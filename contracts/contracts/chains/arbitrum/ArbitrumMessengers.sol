// SPDX-License-Identifier: MIT
pragma solidity ^0.8.12;

import "OpenZeppelin/openzeppelin-contracts@4.7.3/contracts/vendor/arbitrum/IArbSys.sol";
import "OpenZeppelin/openzeppelin-contracts@4.7.3/contracts/vendor/arbitrum/IBridge.sol";
import "OpenZeppelin/openzeppelin-contracts@4.7.3/contracts/vendor/arbitrum/IInbox.sol";
import "OpenZeppelin/openzeppelin-contracts@4.7.3/contracts/vendor/arbitrum/IOutbox.sol";
import "OpenZeppelin/openzeppelin-contracts@4.7.3/contracts/access/Ownable.sol";

import "../../../interfaces/IMessenger.sol";
import "../../RestrictedCalls.sol";
import "../../Resolver.sol";

contract ArbitrumL1Messenger is IMessenger, RestrictedCalls {
    IBridge public bridge;
    IInbox public inbox;

    /// Maps addresses to ETH deposits to be used for paying the submission fee.
    mapping(address => uint256) public deposits;

    constructor(address bridge_, address inbox_) {
        bridge = IBridge(bridge_);
        inbox = IInbox(inbox_);
    }

    function callAllowed(address caller, address courier)
        external
        view
        returns (bool)
    {
        // The call from L2 must be delivered by the Arbitrum bridge.
        if (courier != address(bridge)) return false;

        IOutbox outbox = IOutbox(bridge.activeOutbox());
        address sender = outbox.l2ToL1Sender();
        return sender == caller;
    }

    // This is copied verbatim from the Arbitrum Nitro repo.
    // TODO: remove once OpenZeppelin is updated with new Nitro contracts.
    // See https://github.com/OpenZeppelin/openzeppelin-contracts/pull/3692.
    function calculateRetryableSubmissionFee(
        uint256 dataLength,
        uint256 baseFee
    ) public view returns (uint256) {
        // Use current block basefee if baseFee parameter is 0
        return
            (1400 + 6 * dataLength) * (baseFee == 0 ? block.basefee : baseFee);
    }

    function deposit() external payable {
        deposits[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 amount = deposits[msg.sender];
        require(amount > 0, "nothing to withdraw");

        deposits[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "failed to send Ether");
    }

    /* solhint-disable avoid-tx-origin */
    function sendMessage(address target, bytes calldata message)
        external
        restricted(block.chainid)
    {
        uint256 submissionFee = calculateRetryableSubmissionFee(
            message.length,
            0
        );
        require(deposits[tx.origin] >= submissionFee, "insufficient deposit");

        deposits[tx.origin] -= submissionFee;

        // We set maxGas to 100_000. We also set gasPriceBid to 0 because the
        // relayer will redeem the ticket on L2 and we only want to pay the
        // submission cost on L1.
        inbox.createRetryableTicket{value: submissionFee}(
            target,
            0,
            submissionFee,
            tx.origin,
            tx.origin,
            100_000,
            0,
            message
        );
    }
    /* solhint-enable avoid-tx-origin */
}

contract ArbitrumL2Messenger is IMessenger, Ownable, RestrictedCalls {
    function callAllowed(address caller, address courier)
        external
        view
        returns (bool)
    {
        // Arbitrum sets `msg.sender` on calls coming from L1 to be the aliased
        // form of the address that sent the message so we need to check
        // that aliased address here. In our case, that is the L2 alias of our
        // caller, ArbitrumL1Messenger.
        IArbSys arbsys = IArbSys(address(100));
        return
            courier ==
            arbsys.mapL1SenderContractAddressToL2Alias(caller, address(0));
    }

    function sendMessage(address target, bytes calldata message)
        external
        restricted(block.chainid)
    {
        IArbSys arbsys = IArbSys(address(100));
        arbsys.sendTxToL1(target, message);
    }
}