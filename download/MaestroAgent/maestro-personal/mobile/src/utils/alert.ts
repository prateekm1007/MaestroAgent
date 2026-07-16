/**
 * Cross-platform alert helper.
 *
 * Uses Alert.alert on native (iOS/Android), window.alert/window.confirm on web.
 * React Native's Alert.alert is a no-op on web — this wrapper ensures
 * alerts work everywhere.
 */
import { Alert, Platform } from 'react-native';

type AlertButton = {
  text: string;
  onPress?: () => void;
  style?: 'default' | 'cancel' | 'destructive';
};

export function showAlert(
  title: string,
  message?: string,
  buttons?: AlertButton[],
): void {
  if (Platform.OS === 'web') {
    if (buttons && buttons.length > 1) {
      const ok = window.confirm(message ? `${title}\n\n${message}` : title);
      const destructiveBtn = buttons.find((b) => b.style === 'destructive');
      const defaultBtn = buttons.find((b) => b.style !== 'cancel' && b.style !== 'destructive') || buttons[0];
      if (ok && (destructiveBtn?.onPress || defaultBtn?.onPress)) {
        (destructiveBtn || defaultBtn).onPress?.();
      }
    } else {
      window.alert(message ? `${title}\n\n${message}` : title);
      if (buttons && buttons[0]?.onPress) {
        buttons[0].onPress();
      }
    }
  } else {
    if (buttons) {
      Alert.alert(title, message, buttons);
    } else {
      Alert.alert(title, message);
    }
  }
}
