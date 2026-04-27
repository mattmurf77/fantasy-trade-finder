import { create } from 'zustand';

// Tiny ephemeral store coordinating the iOS "Allow notifications?" prompt.
// usePushNotifications flips `pending=true` when permission is still
// `undetermined` and the user has hit the trigger event (rankings unlocked
// → first match imminent). PushPrimingModal listens on `pending`, renders
// the in-app priming sheet, and on Accept calls the registered handler
// (which performs Notifications.requestPermissionsAsync + token register).
interface PrimingState {
  pending: boolean;
  // Set by the hook so the modal's Accept tap can re-enter the registration
  // flow without us re-mounting the hook.
  acceptHandler: (() => Promise<void>) | null;

  request(handler: () => Promise<void>): void;
  dismiss(): void;
  clear(): void;
}

export const usePushPriming = create<PrimingState>((set) => ({
  pending: false,
  acceptHandler: null,

  request(handler) {
    set({ pending: true, acceptHandler: handler });
  },
  dismiss() {
    set({ pending: false, acceptHandler: null });
  },
  clear() {
    set({ pending: false, acceptHandler: null });
  },
}));
