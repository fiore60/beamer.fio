import { mount } from '@vue/test-utils';
import { markRaw } from 'vue';

import Tabs from '@/components/layout/Tabs.vue';
import { getRandomString } from '~/utils/data_generators';

function createWrapper(options?: {
  tabs: Array<{ label?: string; template?: string }>;
  activeTabLabel?: string;
}) {
  const tabs = (options?.tabs ?? []).map((tab) => ({
    label: tab.label ?? getRandomString(),
    content: markRaw({ template: tab.template ?? '<div />' }),
  }));

  return mount(Tabs, {
    shallow: false,
    props: { tabs, activeTabLabel: options?.activeTabLabel },
  });
}

describe('Tabs.vue', () => {
  it('renders the label of each tab', () => {
    const tabs = [{ label: 'foo' }, { label: 'bar' }, { label: 'baz' }];
    const wrapper = createWrapper({ tabs });
    const tabHeaders = wrapper.findAll('[data-test="tab-header"]');

    expect(tabHeaders.length).toBe(3);
    expect(tabHeaders[0].text()).toContain('foo');
    expect(tabHeaders[1].text()).toContain('bar');
    expect(tabHeaders[2].text()).toContain('baz');
  });

  it('shows first tab content per default', () => {
    const tabs = [{ template: 'foo' }, { template: 'bar' }, { template: 'baz' }];
    const wrapper = createWrapper({ tabs });
    const tabContent = wrapper.get('[data-test="tab-content"]');

    expect(tabContent.html()).toContain('foo');
  });

  it('can alternate first open tab via property', () => {
    const tabs = [{ template: 'foo' }, { label: 'bar', template: 'bar' }];
    const wrapper = createWrapper({ tabs, activeTabLabel: 'bar' });
    const tabContent = wrapper.get('[data-test="tab-content"]');

    expect(tabContent.html()).toContain('bar');
  });

  it('can switch tab content via clicks on the headers', async () => {
    const tabs = [{ template: 'foo' }, { template: 'bar' }, { template: 'baz' }];
    const wrapper = createWrapper({ tabs });
    const tabHeaders = wrapper.findAll('[data-test="tab-header"]');
    const tabContent = wrapper.get('[data-test="tab-content"]');

    expect(tabContent.html()).toContain('foo');
    await tabHeaders[1].trigger('click');
    expect(tabContent.html()).toContain('bar');
    await tabHeaders[2].trigger('click');
    expect(tabContent.html()).toContain('baz');
    await tabHeaders[1].trigger('click');
    expect(tabContent.html()).toContain('bar');
    await tabHeaders[0].trigger('click');
    expect(tabContent.html()).toContain('foo');
  });

  it('can switch tab content via alternating the related property', async () => {
    const tabs = [
      { label: 'foo', template: 'foo' },
      { label: 'bar', template: 'bar' },
      { label: 'baz', template: 'baz' },
    ];
    const wrapper = createWrapper({ tabs });
    const tabContent = wrapper.get('[data-test="tab-content"]');

    expect(tabContent.html()).toContain('foo');
    await wrapper.setProps({ ...wrapper.props, activeTabLabel: 'bar' });
    expect(tabContent.html()).toContain('bar');
    await wrapper.setProps({ ...wrapper.props, activeTabLabel: 'baz' });
    expect(tabContent.html()).toContain('baz');
    await wrapper.setProps({ ...wrapper.props, activeTabLabel: 'bar' });
    expect(tabContent.html()).toContain('bar');
    await wrapper.setProps({ ...wrapper.props, activeTabLabel: 'foo' });
    expect(tabContent.html()).toContain('foo');
  });

  it('does nothing if trying to switch to unknown tab', async () => {
    const tabs = [
      { label: 'foo', template: 'foo' },
      { label: 'bar', template: 'bar' },
    ];
    const wrapper = createWrapper({ tabs });
    const tabContent = wrapper.get('[data-test="tab-content"]');
    expect(tabContent.html()).toContain('foo');

    await wrapper.setProps({ ...wrapper.props, activeTabLabel: 'baz' });

    expect(tabContent.html()).toContain('foo');
  });

  it('does not unload content component when tab changes', async () => {
    const tabs = [{ template: '<input id="test-input" />' }, { template: 'bar' }];
    const wrapper = createWrapper({ tabs });
    const tabHeaders = wrapper.findAll('[data-test="tab-header"]');

    // Just a stupid helper to get around typing issues.
    const getInputValue = () => (wrapper.find('#test-input').element as HTMLInputElement).value;

    await wrapper.get('#test-input').setValue('test value');
    expect(getInputValue()).toBe('test value');
    await tabHeaders[1].trigger('click');
    expect(wrapper.find('#test-input').exists()).toBeFalsy();
    await tabHeaders[0].trigger('click');
    expect(getInputValue()).toBe('test value');
  });
});
