import { View } from 'react-native';
import type { Marker } from '../types';

const TYPE_COLOR: Record<string, string> = {
  defect:       '#ef4444',
  ai_detection: '#f97316',
  measurement:  '#3b82f6',
  note:         '#22c55e',
};

interface Props {
  markers: Marker[];
  /** Rendered pixel size of the image this overlay sits on */
  width: number;
  height: number;
}

/**
 * Absolute-positioned marker overlay for React Native.
 * Place inside a View that wraps an <Image /> with matching width/height.
 *
 * NOTE: <canvas> + <img> is web-only DOM API — it does not exist in RN.
 * This component uses View-based drawing which works on iOS, Android, and Expo Web.
 */
export default function MarkerOverlay({ markers, width, height }: Props) {
  if (!markers.length) return null;

  return (
    <View
      style={{ position: 'absolute', top: 0, left: 0, width, height }}
      pointerEvents="none"
    >
      {markers.map((m) => {
        const color = TYPE_COLOR[m.markerType] ?? '#ef4444';
        const borderWidth = m.markerSource === 'ai' ? 1.5 : 2;

        if (m.width != null && m.height != null) {
          // Bounding-box marker
          return (
            <View
              key={m.id}
              style={{
                position: 'absolute',
                left: m.x * width,
                top: m.y * height,
                width: m.width * width,
                height: m.height * height,
                borderWidth,
                borderColor: color,
              }}
            />
          );
        }

        // Point marker — filled circle
        const R = 5;
        return (
          <View
            key={m.id}
            style={{
              position: 'absolute',
              left: m.x * width - R,
              top: m.y * height - R,
              width: R * 2,
              height: R * 2,
              borderRadius: R,
              borderWidth,
              borderColor: color,
              backgroundColor: color + '40', // 25 % opacity fill
            }}
          />
        );
      })}
    </View>
  );
}
