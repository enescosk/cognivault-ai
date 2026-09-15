import {afterEach, describe, expect, it, vi} from 'vitest';
import {TurnRecorder} from './recorder';

afterEach(() => {vi.unstubAllGlobals(); vi.useRealTimers();});

describe('TurnRecorder lifecycle', () => {
  it('stops a microphone granted after the user has cancelled', async () => {
    let resolve!: (stream: MediaStream) => void;
    const stop = vi.fn();
    vi.stubGlobal('navigator', {mediaDevices: {getUserMedia: () => new Promise<MediaStream>(r => {resolve = r;})}});
    vi.stubGlobal('MediaRecorder', class {});
    const recorder = new TurnRecorder();
    const audio = vi.fn(), error = vi.fn();
    const pending = recorder.start(audio, error, vi.fn());
    recorder.stop(true);
    resolve({getTracks: () => [{stop}]} as unknown as MediaStream);
    await pending;
    expect(stop).toHaveBeenCalledOnce();
    expect(audio).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });

  it('reports permission rejection without producing a fake transcript', async () => {
    vi.stubGlobal('navigator', {mediaDevices: {getUserMedia: () => Promise.reject(new DOMException('denied', 'NotAllowedError'))}});
    vi.stubGlobal('MediaRecorder', class {});
    const audio = vi.fn(), error = vi.fn();
    await new TurnRecorder().start(audio, error, vi.fn());
    expect(error).toHaveBeenCalledWith(expect.stringContaining('Mikrofon izni'));
    expect(audio).not.toHaveBeenCalled();
  });

  it('keeps a phrase open through a one-second pause, then emits only once', async () => {
    vi.useFakeTimers();
    let amplitude = 0.08;
    const trackStop = vi.fn();
    const getUserMedia = vi.fn(async () => ({getTracks: () => [{stop: trackStop}]}));
    vi.stubGlobal('navigator', {mediaDevices: {getUserMedia}});
    class MockRecorder {
      static isTypeSupported = () => true;
      state = 'inactive'; mimeType = 'audio/webm';
      ondataavailable?: (event: {data: Blob}) => void;
      onstop?: () => void;
      start() {this.state = 'recording';}
      stop() {this.state = 'inactive'; this.ondataavailable?.({data: new Blob(['x'.repeat(2000)])}); this.onstop?.();}
    }
    vi.stubGlobal('MediaRecorder', MockRecorder);
    vi.stubGlobal('AudioContext', class {
      state = 'running';
      resume = async () => {};
      close = async () => {this.state = 'closed';};
      createMediaStreamSource = () => ({connect: vi.fn()});
      createAnalyser = () => ({fftSize: 2048, getFloatTimeDomainData: (buffer: Float32Array) => buffer.fill(amplitude)});
    });
    const audio = vi.fn(), error = vi.fn();
    await new TurnRecorder().start(audio, error, vi.fn());
    await vi.advanceTimersByTimeAsync(400);
    amplitude = 0;
    await vi.advanceTimersByTimeAsync(1000);
    expect(audio).not.toHaveBeenCalled();
    amplitude = 0.08;
    await vi.advanceTimersByTimeAsync(400);
    amplitude = 0;
    await vi.advanceTimersByTimeAsync(1500);
    expect(audio).toHaveBeenCalledOnce();
    expect(error).not.toHaveBeenCalled();
    expect(trackStop).toHaveBeenCalledOnce();
  });
});
