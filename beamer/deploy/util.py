from pathlib import Path
from typing import Any, Sequence, Union, cast

import structlog
from eth_typing import ChecksumAddress
from eth_utils import encode_hex, to_wei
from web3 import Web3
from web3.contract import Contract, ContractConstructor
from web3.contract.contract import ContractFunction

from beamer.artifacts import ChainDeployment, DeployedContractInfo, Deployment
from beamer.chains import get_chain_descriptor
from beamer.contracts import ABIManager
from beamer.deploy import config
from beamer.typing import BlockNumber, ChainId
from beamer.util import get_commit_id, transact

log = structlog.get_logger(__name__)


class DeployedContract(Contract):
    deployment_block: BlockNumber
    deployment_txhash: str
    deployment_args: list[Any]
    name: str


def _transact(func: Union[ContractConstructor, ContractFunction]) -> Any:
    return transact(func, timeout=600, poll_latency=1)


def deploy_contract(
    web3: Web3, abi_manager: ABIManager, constructor_spec: Union[str, Sequence]
) -> DeployedContract:
    # constructor_spec is either
    # 1) a contract name e.g. "Foo", or
    # 2) a sequence containing the contract name and
    #    constructor arguments, e.g. ["Foo", "0x1CEE82EEd89Bd5Be5bf2507a92a755dcF1D8e8dc"]
    if isinstance(constructor_spec, str):
        name = constructor_spec
        args: Sequence = ()
    else:
        name = constructor_spec[0]
        args = constructor_spec[1:]

    abi = abi_manager.get_abi(name)
    bytecode = abi_manager.get_bytecode(name)

    log.info("Deploying contract", contract=name)
    ContractFactory = cast(Contract, web3.eth.contract(abi=abi, bytecode=bytecode))

    receipt = _transact(ContractFactory.constructor(*args))
    txhash = encode_hex(receipt.transactionHash)

    address = receipt.contractAddress
    deployed = cast(DeployedContract, web3.eth.contract(address=address, abi=abi))
    deployed.deployment_block = receipt.blockNumber
    deployed.deployment_txhash = txhash
    deployed.deployment_args = list(args)
    deployed.name = name

    log.info("Deployed contract", contract=name, address=address, txhash=txhash)
    return deployed


def _resolve_constructor_args(
    contract_args: dict[str, Contract], constructor_spec: str | Sequence
) -> tuple:
    if isinstance(constructor_spec, str):
        # This is just the contract's name.
        return (constructor_spec,)
    return tuple(
        contract_args[arg].address if "$" in str(arg) else arg for arg in constructor_spec
    )


def deploy_beamer(
    w3: Web3, abi_manager: ABIManager, chain: config.Chain, resolver: Contract
) -> tuple[tuple[DeployedContract, ...], tuple[DeployedContract, ...]]:
    contract_args = {"${resolver}": resolver}
    request_manager = deploy_contract(
        w3,
        abi_manager,
        (
            "RequestManager",
            to_wei(chain.request_manager_arguments.claim_stake, "ether"),
            chain.request_manager_arguments.claim_request_extension,
            chain.request_manager_arguments.claim_period,
            chain.request_manager_arguments.challenge_period_extension,
        ),
    )
    contract_args["${request_manager}"] = request_manager
    args = _resolve_constructor_args(contract_args, chain.l1_messenger)
    l1_messenger = deploy_contract(resolver.w3, abi_manager, args)

    args = _resolve_constructor_args(contract_args, chain.l2_messenger)
    l2_messenger = deploy_contract(w3, abi_manager, args)

    chain_descriptor = get_chain_descriptor(chain.chain_id)
    assert chain_descriptor is not None

    if chain_descriptor.ecosystem_name == "polygon_zkevm":
        _transact(l1_messenger.functions.setRemoteMessenger(l2_messenger.address))
        _transact(l2_messenger.functions.setRemoteMessenger(l1_messenger.address))

    fill_manager = deploy_contract(w3, abi_manager, ("FillManager", l2_messenger.address))
    _transact(fill_manager.functions.setResolver(resolver.address))

    # Authorize call chain
    _transact(l2_messenger.functions.addCaller(fill_manager.address))
    _transact(
        resolver.functions.addCaller(
            chain.chain_id,
            l2_messenger.address,
            l1_messenger.address,
        )
    )
    _transact(
        resolver.functions.addRequestManager(
            chain.chain_id, request_manager.address, l1_messenger.address
        )
    )
    _transact(l1_messenger.functions.addCaller(resolver.address))
    _transact(
        request_manager.functions.addCaller(
            l1_messenger.w3.eth.chain_id,
            l1_messenger.address,
            l2_messenger.address,
        )
    )

    l1_contracts = (l1_messenger,)
    l2_contracts = request_manager, fill_manager, l2_messenger
    return l1_contracts, l2_contracts


def _make_deployed_contract_info(contract: DeployedContract) -> DeployedContractInfo:
    beamer_commit = get_commit_id()
    return DeployedContractInfo(
        beamer_commit=beamer_commit,
        tx_hash=contract.deployment_txhash,
        address=contract.address,
        deployment_block=contract.deployment_block,
        deployment_args=contract.deployment_args,
    )


def generate_artifacts(
    path: Path,
    deployer: ChecksumAddress,
    base: Sequence[DeployedContract],
    chain: Sequence[DeployedContract] = (),
) -> None:
    base_contracts = {}
    for contract in base:
        base_contracts[contract.name] = _make_deployed_contract_info(contract)

    chain_contracts = {}
    for contract in chain:
        chain_contracts[contract.name] = _make_deployed_contract_info(contract)

    base_chain_id = ChainId(next(iter(base)).w3.eth.chain_id)
    base_deployment = ChainDeployment(chain_id=base_chain_id, contracts=base_contracts)

    if chain_contracts:
        chain_id = ChainId(next(iter(chain)).w3.eth.chain_id)
        chain_deployment = ChainDeployment(chain_id=chain_id, contracts=chain_contracts)
    else:
        chain_deployment = None

    deployment = Deployment(deployer=deployer, base=base_deployment, chain=chain_deployment)
    deployment.to_file(path)
