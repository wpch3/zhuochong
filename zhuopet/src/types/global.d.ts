export {};

declare global {
  interface Window {
    zhuopet?: {
      quit?: () => void;
      setIgnoreMouseEvents?: (ignore: boolean) => void;
      setAlwaysOnTop?: (value: boolean) => void;
      minimize?: () => void;
      platform?: string;
      togglePetWindow?: () => void;
      openChat?: () => void;
      openSettings?: () => void;
      onOpenChat?: (callback: () => void) => () => void;
      onOpenSettings?: (callback: () => void) => () => void;
      onOpenStudio?: (callback: () => void) => () => void;
      onClickThrough?: (callback: (value: boolean) => void) => () => void;
    };
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    webkitAudioContext?: typeof AudioContext;
  }

  interface SpeechRecognitionLike {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    maxAlternatives: number;
    start: () => void;
    stop: () => void;
    abort: () => void;
    onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
  }
}
