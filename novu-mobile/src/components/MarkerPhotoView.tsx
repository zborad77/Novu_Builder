import { useState, useCallback } from 'react';
import { View, Image, Pressable, StyleSheet } from 'react-native';
import type { GestureResponderEvent, StyleProp, ViewStyle } from 'react-native';
import MarkerOverlay from './MarkerOverlay';
import type { Marker } from '../types';

interface Props {
  uri: string;
  markers: Marker[];
  /**
   * Called with normalised 0–1 coordinates when the user taps the image.
   * Omit to make the view non-interactive (display-only).
   */
  onTap?: (x: number, y: number) => void;
  /**
   * Container style. Pass explicit width+height for thumbnails,
   * or omit to get full-width with 4:3 aspect ratio.
   */
  style?: StyleProp<ViewStyle>;
}

/**
 * Image with an absolute marker overlay for React Native.
 *
 * Replaces the web-only <canvas>/<img> approach:
 *   - Dimensions come from onLayout (actual rendered size), not getBoundingClientRect
 *   - Touch position comes from nativeEvent.locationX/Y (already relative), not clientX - rect.left
 *   - Rendering uses <View> borders, not ctx.strokeRect
 */
export default function MarkerPhotoView({ uri, markers, onTap, style }: Props) {
  const [size, setSize] = useState({ width: 0, height: 0 });

  const handleLayout = useCallback(
    (e: { nativeEvent: { layout: { width: number; height: number } } }) => {
      const { width, height } = e.nativeEvent.layout;
      setSize({ width, height });
    },
    [],
  );

  const handlePress = useCallback(
    (e: GestureResponderEvent) => {
      if (!onTap || !size.width || !size.height) return;
      const x = e.nativeEvent.locationX / size.width;
      const y = e.nativeEvent.locationY / size.height;
      onTap(
        Math.max(0, Math.min(1, x)),
        Math.max(0, Math.min(1, y)),
      );
    },
    [onTap, size],
  );

  const container: StyleProp<ViewStyle> = [
    styles.container,
    style,
  ];

  return (
    <Pressable onLayout={handleLayout} onPress={onTap ? handlePress : undefined} style={container}>
      <Image source={{ uri }} style={styles.image} resizeMode="cover" />
      <MarkerOverlay markers={markers} width={size.width} height={size.height} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'relative',
    overflow: 'hidden',
    // default: full width with 4:3 ratio — overridden by explicit style prop
    width: '100%',
    aspectRatio: 4 / 3,
  },
  image: {
    width: '100%',
    height: '100%',
  },
});
