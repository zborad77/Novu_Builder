import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  FlatList,
  Image,
  Alert,
} from 'react-native';
import { useLocalSearchParams, useNavigation } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { PROJECT_STATUS_LABELS } from '../../src/types';
import { TokenStorage, PhotosApi } from '../../src/services/api';
import Constants from 'expo-constants';

interface ProjectPhoto {
  id: string;
  variants?: { thumbnail?: { url: string }; medium?: { url: string } };
  url?: string;
  filename: string;
}

interface ProjectDetail {
  id: string;
  title: string;
  description: string | null;
  status: string;
  source: string;
  propertyType: string | null;
  repairScope: string | null;
  location: {
    lat: number | null;
    lng: number | null;
    addressLabel: string | null;
  };
  photos: ProjectPhoto[];
  proposalDraft: { subject: string | null; totalPrice: number | null } | null;
  createdAt: string | null;
  updatedAt: string | null;
}

const STATUS_COLOR: Record<string, string> = {
  new: '#1565C0',
  in_progress: '#E65100',
  draft: '#6A1B9A',
  ready: '#2E7D32',
  sent: '#00838F',
  archived: '#546E7A',
};

function getBaseUrl(): string {
  const extra = Constants.expoConfig?.extra as { apiUrl?: string } | undefined;
  return extra?.apiUrl ?? 'http://localhost:8000/api/v1';
}

function photoThumbUrl(photo: ProjectPhoto, baseUrl: string): string {
  const thumb = photo.variants?.thumbnail?.url ?? photo.variants?.medium?.url ?? photo.url ?? '';
  if (!thumb) return '';
  if (thumb.startsWith('http')) return thumb;
  // Strip /api/v1 suffix from baseUrl to get host
  const host = baseUrl.replace(/\/api.*/, '');
  return `${host}${thumb}`;
}

async function fetchProjectDetail(id: string): Promise<ProjectDetail> {
  const token = await TokenStorage.getAccessToken();
  const res = await fetch(`${getBaseUrl()}/cases/${id}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const navigation = useNavigation();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const data = await fetchProjectDetail(id);
      setProject(data);
      navigation.setOptions({ title: data.title });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Chyba při načítání.');
    } finally {
      setLoading(false);
    }
  }, [id, navigation]);

  useEffect(() => { load(); }, [load]);

  const uploadPhoto = useCallback(async (uri: string, filename: string) => {
    if (!id) return;
    setUploading(true);
    try {
      await PhotosApi.upload(id, uri, filename);
      await load();
    } catch (err: unknown) {
      Alert.alert('Chyba', err instanceof Error ? err.message : 'Nahrání fotky selhalo.');
    } finally {
      setUploading(false);
    }
  }, [id, load]);

  const handleTakePhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Přístup odepřen', 'Povolte přístup ke kameře v nastavení.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8 });
    if (!result.canceled) {
      const a = result.assets[0];
      await uploadPhoto(a.uri, a.fileName ?? `photo_${Date.now()}.jpg`);
    }
  }, [uploadPhoto]);

  const handleSendForAnalysis = useCallback(async () => {
    if (!id) return;
    Alert.alert(
      'Odeslat ke zpracování',
      'Zakázka bude odeslána na server ke zpracování. Pokračovat?',
      [
        { text: 'Zrušit', style: 'cancel' },
        {
          text: 'Odeslat',
          onPress: async () => {
            setSending(true);
            try {
              const token = await TokenStorage.getAccessToken();
              const res = await fetch(`${getBaseUrl()}/cases/${id}/analysis-jobs`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
              });
              if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail ?? `HTTP ${res.status}`);
              }
              Alert.alert('Hotovo', 'Zakázka byla odeslána ke zpracování.');
              await load();
            } catch (err: unknown) {
              Alert.alert('Chyba', err instanceof Error ? err.message : 'Odeslání selhalo.');
            } finally {
              setSending(false);
            }
          },
        },
      ],
    );
  }, [id, load]);

  const handlePickPhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Přístup odepřen', 'Povolte přístup k fotkám v nastavení.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      quality: 0.8,
    });
    if (!result.canceled) {
      for (const a of result.assets) {
        await uploadPhoto(a.uri, a.fileName ?? `photo_${Date.now()}.jpg`);
      }
    }
  }, [uploadPhoto]);

  if (loading) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#1565C0" /></View>;
  }

  if (error || !project) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error ?? 'Zakázka nenalezena.'}</Text>
        <TouchableOpacity onPress={load}><Text style={styles.retryText}>Zkusit znovu</Text></TouchableOpacity>
      </View>
    );
  }

  const statusLabel = PROJECT_STATUS_LABELS[project.status] ?? project.status;
  const statusColor = STATUS_COLOR[project.status] ?? '#546E7A';
  const baseUrl = getBaseUrl();

  return (
    <ScrollView style={styles.container}>
      {/* Hlavička */}
      <View style={styles.headerCard}>
        <View style={[styles.badge, { backgroundColor: statusColor }]}>
          <Text style={styles.badgeText}>{statusLabel}</Text>
        </View>
        <Text style={styles.title}>{project.title}</Text>
        {project.description ? (
          <Text style={styles.description}>{project.description}</Text>
        ) : null}
      </View>

      {/* Informace */}
      <InfoCard title="Informace o objektu">
        <InfoRow label="Typ objektu" value={project.propertyType ?? '—'} />
        <InfoRow label="Rozsah opravy" value={project.repairScope ?? '—'} />
        <InfoRow label="Zdroj" value={project.source === 'mobile' ? '📱 Mobil' : '🖥 Desktop'} />
      </InfoCard>

      {/* Poloha */}
      <InfoCard title="Poloha">
        <InfoRow label="Adresa" value={project.location.addressLabel ?? '—'} />
        {project.location.lat != null && (
          <InfoRow
            label="GPS"
            value={`${project.location.lat.toFixed(5)}, ${project.location.lng?.toFixed(5)}`}
          />
        )}
      </InfoCard>

      {/* Nabídka */}
      {project.proposalDraft && (
        <InfoCard title="Návrh nabídky">
          {project.proposalDraft.subject && (
            <InfoRow label="Předmět" value={project.proposalDraft.subject} />
          )}
          {project.proposalDraft.totalPrice != null && (
            <InfoRow
              label="Celková cena"
              value={`${project.proposalDraft.totalPrice.toLocaleString('cs-CZ')} Kč`}
            />
          )}
        </InfoCard>
      )}

      {/* Fotky */}
      <View style={styles.photosCard}>
        <Text style={styles.cardTitle}>Fotky ({project.photos.length})</Text>

        <View style={styles.photoButtons}>
          <TouchableOpacity
            style={[styles.photoBtn, uploading && styles.btnDisabled]}
            onPress={handleTakePhoto}
            disabled={uploading}
          >
            <Text style={styles.photoBtnText}>📷 Vyfotit</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.photoBtn, styles.photoBtnOutline, uploading && styles.btnDisabled]}
            onPress={handlePickPhoto}
            disabled={uploading}
          >
            <Text style={[styles.photoBtnText, styles.photoBtnTextOutline]}>🖼 Z galerie</Text>
          </TouchableOpacity>
        </View>

        {uploading && (
          <View style={styles.uploadingRow}>
            <ActivityIndicator size="small" color="#1565C0" />
            <Text style={styles.uploadingText}>Nahrávám…</Text>
          </View>
        )}

        {project.photos.length > 0 && (
          <FlatList
            horizontal
            data={project.photos}
            keyExtractor={(p) => p.id}
            renderItem={({ item }) => {
              const uri = photoThumbUrl(item, baseUrl);
              return uri ? (
                <Image source={{ uri }} style={styles.photoThumb} />
              ) : null;
            }}
            style={{ marginTop: 12 }}
            contentContainerStyle={{ gap: 8 }}
          />
        )}
      </View>

      {/* Odeslat ke zpracování */}
      <View style={styles.sendRow}>
        <TouchableOpacity
          style={[styles.sendBtn, (sending || uploading) && styles.btnDisabled]}
          onPress={handleSendForAnalysis}
          disabled={sending || uploading}
        >
          {sending ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.sendBtnText}>🚀 Odeslat ke zpracování</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Časy */}
      <InfoCard title="Časové razítko">
        {project.createdAt && (
          <InfoRow label="Vytvořeno" value={new Date(project.createdAt).toLocaleString('cs-CZ')} />
        )}
        {project.updatedAt && (
          <InfoRow label="Aktualizováno" value={new Date(project.updatedAt).toLocaleString('cs-CZ')} />
        )}
      </InfoCard>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.infoCard}>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F5F7FA' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  errorText: { color: '#C62828', fontSize: 15, marginBottom: 12 },
  retryText: { color: '#1565C0', fontSize: 15, fontWeight: '600' },
  headerCard: {
    backgroundColor: '#fff',
    margin: 16,
    marginBottom: 8,
    borderRadius: 12,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginBottom: 10,
  },
  badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  title: { fontSize: 18, fontWeight: '800', color: '#212121', marginBottom: 6 },
  description: { fontSize: 14, color: '#546E7A', lineHeight: 20 },
  infoCard: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 1,
  },
  cardTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: '#546E7A',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 10,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  infoLabel: { color: '#78909C', fontSize: 14, flex: 1 },
  infoValue: { color: '#212121', fontSize: 14, fontWeight: '600', flex: 1, textAlign: 'right' },
  photosCard: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 1,
  },
  photoButtons: { flexDirection: 'row', gap: 10 },
  photoBtn: {
    flex: 1,
    backgroundColor: '#1565C0',
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
  },
  photoBtnOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: '#1565C0',
  },
  photoBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  photoBtnTextOutline: { color: '#1565C0' },
  btnDisabled: { opacity: 0.5 },
  uploadingRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  uploadingText: { color: '#546E7A', fontSize: 13 },
  photoThumb: { width: 100, height: 100, borderRadius: 8 },
  sendRow: { marginHorizontal: 16, marginTop: 8, marginBottom: 4 },
  sendBtn: {
    backgroundColor: '#2E7D32',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  sendBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
