// @vitest-environment jsdom
import { describe, expect, it, beforeAll, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import App from '../src/App';
import { usePetStore } from '../src/store/usePetStore';

beforeAll(() => {
  // jsdom gaps
  globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(performance.now()), 16) as unknown as number) as typeof requestAnimationFrame;
  globalThis.cancelAnimationFrame = ((id: number) => clearTimeout(id)) as typeof cancelAnimationFrame;
  Element.prototype.scrollIntoView = () => {};
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.hasPointerCapture = () => false;
  window.confirm = () => true;
});

beforeEach(() => {
  localStorage.clear();
  usePetStore.setState({
    characterId: 'xiaoxun',
    onboarded: true,
    messages: [],
    facts: [],
    moments: [],
    userName: '测试',
    affection: 24,
    energy: 1,
    emotion: 'neutral',
    sleeping: false,
    isReplying: false,
    streamingText: '',
    chatOpen: false,
    settingsOpen: false,
    studioOpen: false,
    memoryOpen: false,
    dressupOpen: false,
    contextMenu: null,
    effects: [],
    bubble: null,
    toast: null,
    lastInteractionAt: Date.now(),
  });
});

afterEach(() => {
  cleanup();
  usePetStore.setState({ isReplying: false, streamingText: '', messages: [], facts: [] });
});

describe('ZhuoPet app', () => {
  it('renders the desktop, pet and dock', () => {
    render(<App />);
    expect(screen.getByText('ZhuoPet')).toBeTruthy();
    expect(document.querySelector('.pet-svg svg')).toBeTruthy();
    expect(screen.getByText('说话')).toBeTruthy();
    expect(screen.getByText('换装')).toBeTruthy();
    expect(screen.getByText('记忆')).toBeTruthy();
  });

  it('opens the chat and gets a local reply', async () => {
    render(<App />);
    fireEvent.click(screen.getByText('说话'));
    const textarea = await screen.findByPlaceholderText(/说点什么/);
    fireEvent.change(textarea, { target: { value: '你好呀' } });
    fireEvent.click(screen.getByTitle('发送'));
    await waitFor(
      () => {
        expect(document.querySelectorAll('.msg.pet').length).toBeGreaterThan(1);
      },
      { timeout: 5000 },
    );
    expect(document.querySelector('.chat-panel')).toBeTruthy();
  }, 15000);

  it('remembers a fact and shows it in the memory tab', async () => {
    render(<App />);
    fireEvent.click(screen.getByText('说话'));
    const textarea = await screen.findByPlaceholderText(/说点什么/);
    fireEvent.change(textarea, { target: { value: '记住，我喜欢草莓牛奶' } });
    fireEvent.click(screen.getByTitle('发送'));
    await waitFor(() => expect(usePetStore.getState().facts.length).toBeGreaterThan(0), { timeout: 5000 });
    fireEvent.click(screen.getByText(/记忆 ·/));
    await waitFor(() => expect(document.querySelector('.fact-text')?.textContent ?? '').toContain('草莓牛奶'), { timeout: 3000 });
  }, 15000);

  it('shows onboarding on first run and saves the name', async () => {
    usePetStore.setState({ onboarded: false, messages: [], userName: '' });
    render(<App />);
    expect(screen.getByText(/初次见面/)).toBeTruthy();
    const input = screen.getByPlaceholderText(/你的名字或昵称/);
    fireEvent.change(input, { target: { value: '阿宁' } });
    fireEvent.click(screen.getByText(/开始和/));
    await waitFor(() => expect(usePetStore.getState().onboarded).toBe(true));
    expect(usePetStore.getState().userName).toBe('阿宁');
    expect(screen.queryByText(/初次见面/)).toBeNull();
  }, 15000);

  it('opens settings and switches tabs', async () => {
    render(<App />);
    fireEvent.click(screen.getAllByTitle('设置')[0]);
    expect(screen.getByText('把桌宠调成你喜欢的样子')).toBeTruthy();
    fireEvent.click(screen.getByText('模型与隐私'));
    expect(screen.getByText('大脑')).toBeTruthy();
    fireEvent.click(screen.getByText('关于'));
    expect(screen.getByText(/ZhuoPet · 桌宠/)).toBeTruthy();
  }, 15000);

  it('opens the model studio', async () => {
    render(<App />);
    fireEvent.click(screen.getByTitle('模型工坊'));
    expect(screen.getByText('模型工坊')).toBeTruthy();
    expect(screen.getByText('骨骼')).toBeTruthy();
    expect(screen.getByText('网格')).toBeTruthy();
  }, 15000);
});
