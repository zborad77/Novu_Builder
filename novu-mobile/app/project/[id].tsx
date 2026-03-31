import { useEffect, useState, useCallback, useRef } from 'react';
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
import { PhotosApi, AnalysisApi, ProjectsApi, getBaseUrl } from '../../src/services/api';


// ── Types ────────────────────────────────────────────────────────────────────

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

interface AnalysisMaterial {
  name: string;
  unit: string;
  quantity: number;
  unitPrice: number;
  totalPrice: number;
}

interface AnalysisWorkflowStep {
  step: number;
  name: string;
  description: string;
  estimatedHours: number;
}

interface AnalysisResult {
  id: string;
  objectType: string | null;
  surfaceCondition: string | null;
  recommendedScope: string | null;
  estimatedAreaSqm: number | null;
  areaConfidence: number | null;
  materials: AnalysisMaterial[] | null;
  workflowSteps: AnalysisWorkflowStep[] | null;
  estimatedDurationDays: number | null;
  laborHoursTotal: number | null;
  modelName: string | null;
}

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  new: '#1565C0',
  in_progress: '#E65100',
  draft: '#6A1B9A',
  ready: '#2E7D32',
  sent: '#00838F',
  archived: '#546E7A',
};

const OBJECT_TYPE_LABELS: Record<string, string> = {
  roof: 'Střecha',
  facade: 'Fasáda',
  interior: 'Interiér',
  foundation: 'Základy',
  other: 'Jiné',
};

const SURFACE_CONDITION_LABELS: Record<string, string> = {
  good: 'Dobrý',
  requires_attention: 'Vyžaduje pozornost',
  critical: 'Kritický',
};

const SURFACE_CONDITION_COLORS: Record<string, string> = {
  good: '#2E7D32',
  requires_attention: '#E65100',
  critical: '#C62828',
};

const SCOPE_LABELS: Record<string, string> = {
  cleaning: 'Čištění',
  local_repair: 'Lokální oprava',
  full_reconstruction: 'Celková rekonstrukce',
};

// ── API helpers ───────────────────────────────────────────────────────────────

function photoThumbUrl(photo: ProjectPhoto, baseUrl: string): string {
  const thumb = photo.variants?.thumbnail?.url ?? photo.variants?.medium?.url ?? photo.url ?? '';
  if (!thumb) return '';
  if (thumb.startsWith('http')) return thumb;
  const host = baseUrl.replace(/\/api.*/, '');
  return `${host}${thumb}`;
}

async function fetchProjectDetail(id: string): Promise<ProjectDetail> {
  return ProjectsApi.getDetail<ProjectDetail>(id);
}

async function fetchLatestAnalysisResult(projectId: string): Promise<AnalysisResult | null> {
  try {
    const detail = await ProjectsApi.getDetail<ProjectDetail & { latestAnalysis?: AnalysisResult | null }>(projectId);
    return detail.latestAnalysis ?? null;
  } catch {
    return null;
  }
}

// ── Screen ───────────────────────────────────────────────────────────────────

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const navigation = useNavigation();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [pollingJobId, setPollingJobId] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const [data, result] = await Promise.all([
        fetchProjectDetail(id),
        fetchLatestAnalysisResult(id).catch(() => null),
      ]);
      setProject(data);
      setAnalysisResult(result);
      navigation.setOptions({ title: data.title });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Chyba při načítání.');
    } finally {
      setLoading(false);
    }
  }, [id, navigation]);

  useEffect(() => { load(); }, [load]);

  // Polling cleanup on unmount
  useEffect(() => () => stopPolling(), [stopPolling]);

  const startPolling = useCallback((jobId: string) => {
    setPollingJobId(jobId);
    let attempts = 0;
    pollingRef.current = setInterval(async () => {
      attempts++;
      try {
        const job = await AnalysisApi.getJob(jobId);
        if (job.status === 'completed') {
          stopPolling();
          setPollingJobId(null);
          const result = await fetchLatestAnalysisResult(id!);
          setAnalysisResult(result);
          setAnalysisError(null);
          await load();
        } else if (job.status === 'failed' || job.status === 'error') {
          stopPolling();
          setPollingJobId(null);
          const msg = job.errorMessage ?? 'Analýza selhala z neznámého důvodu.';
          setAnalysisError(msg);
          Alert.alert('Analýza selhala', msg);
        } else if (attempts >= 30) {
          // 30 × 2s = 60s timeout
          stopPolling();
          setPollingJobId(null);
          setAnalysisError('Zpracování trvá příliš dlouho. Zkuste obnovit stránku.');
          Alert.alert('Zpracování trvá déle', 'Výsledek bude zobrazen po dokončení. Obnovte stránku.');
        }
      } catch {
        // network hiccup — ignore, keep polling
      }
    }, 2000);
  }, [id, load, stopPolling]);

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
            setAnalysisError(null);
            try {
              const data = await AnalysisApi.startJob(id!);
              startPolling(data.jobId);
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : 'Odeslání selhalo.';
              Alert.alert('Chyba', msg);
            } finally {
              setSending(false);
            }
          },
        },
      ],
    );
  }, [id, startPolling]);

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
        {pollingJobId ? (
          <View style={styles.pollingRow}>
            <ActivityIndicator size="small" color="#1565C0" />
            <Text style={styles.pollingText}>Analýza probíhá…</Text>
          </View>
        ) : (
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
        )}
      </View>

      {/* Stav analýzy — selhání */}
      {analysisError && !pollingJobId && (
        <View style={styles.analysisErrorCard}>
          <Text style={styles.analysisErrorTitle}>Analýza selhala</Text>
          <Text style={styles.analysisErrorMsg}>{analysisError}</Text>
          <TouchableOpacity onPress={() => setAnalysisError(null)}>
            <Text style={styles.analysisErrorDismiss}>Zavřít</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Výsledek analýzy */}
      {analysisResult && <AnalysisResultCard result={analysisResult} />}

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

// ── Analysis result card ──────────────────────────────────────────────────────

function AnalysisResultCard({ result }: { result: AnalysisResult }) {
  const conditionColor = result.surfaceCondition
    ? SURFACE_CONDITION_COLORS[result.surfaceCondition] ?? '#546E7A'
    : '#546E7A';

  const totalMaterialCost = result.materials?.reduce((s, m) => s + (m.totalPrice ?? 0), 0) ?? 0;

  return (
    <View style={styles.analysisCard}>
      <View style={styles.analysisTitleRow}>
        <Text style={styles.cardTitle}>Výsledek AI analýzy</Text>
        {result.modelName && (
          <Text style={styles.modelBadge}>{result.modelName}</Text>
        )}
      </View>

      {/* Základní info */}
      <InfoRow
        label="Typ objektu"
        value={result.objectType ? (OBJECT_TYPE_LABELS[result.objectType] ?? result.objectType) : '—'}
      />
      <InfoRow
        label="Stav povrchu"
        value={result.surfaceCondition ? (SURFACE_CONDITION_LABELS[result.surfaceCondition] ?? result.surfaceCondition) : '—'}
      />
      <InfoRow
        label="Doporučený rozsah"
        value={result.recommendedScope ? (SCOPE_LABELS[result.recommendedScope] ?? result.recommendedScope) : '—'}
      />
      {result.estimatedAreaSqm != null && (
        <InfoRow
          label="Odhadovaná plocha"
          value={`${result.estimatedAreaSqm.toFixed(1)} m²`}
        />
      )}
      {result.areaConfidence != null && (
        <View style={styles.confidenceRow}>
          <Text style={styles.infoLabel}>Spolehlivost odhadu</Text>
          <View style={styles.confidenceBar}>
            <View style={[styles.confidenceFill, {
              width: `${Math.round(result.areaConfidence * 100)}%` as `${number}%`,
              backgroundColor: result.areaConfidence >= 0.7 ? '#2E7D32' : result.areaConfidence >= 0.4 ? '#E65100' : '#C62828',
            }]} />
          </View>
          <Text style={[styles.infoValue, { color: conditionColor }]}>
            {Math.round(result.areaConfidence * 100)} %
          </Text>
        </View>
      )}
      {result.estimatedDurationDays != null && (
        <InfoRow label="Odhadovaná doba" value={`${result.estimatedDurationDays} dní`} />
      )}
      {result.laborHoursTotal != null && (
        <InfoRow label="Hodin práce" value={`${result.laborHoursTotal} h`} />
      )}

      {/* Materiály */}
      {result.materials && result.materials.length > 0 && (
        <View style={styles.subSection}>
          <Text style={styles.subSectionTitle}>Materiály</Text>
          {result.materials.map((m, i) => (
            <View key={i} style={styles.materialRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.materialName}>{m.name}</Text>
                <Text style={styles.materialDetail}>
                  {m.quantity} {m.unit} × {m.unitPrice.toLocaleString('cs-CZ')} Kč
                </Text>
              </View>
              <Text style={styles.materialTotal}>
                {m.totalPrice.toLocaleString('cs-CZ')} Kč
              </Text>
            </View>
          ))}
          <View style={styles.materialSumRow}>
            <Text style={styles.materialSumLabel}>Celkem materiál</Text>
            <Text style={styles.materialSumValue}>
              {totalMaterialCost.toLocaleString('cs-CZ')} Kč
            </Text>
          </View>
        </View>
      )}

      {/* Pracovní postup */}
      {result.workflowSteps && result.workflowSteps.length > 0 && (
        <View style={styles.subSection}>
          <Text style={styles.subSectionTitle}>Pracovní postup</Text>
          {result.workflowSteps.map((s) => (
            <View key={s.step} style={styles.stepRow}>
              <View style={styles.stepNumber}>
                <Text style={styles.stepNumberText}>{s.step}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.stepName}>{s.name}</Text>
                {s.description ? (
                  <Text style={styles.stepDesc}>{s.description}</Text>
                ) : null}
                <Text style={styles.stepHours}>{s.estimatedHours} h</Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Styles ────────────────────────────────────────────────────────────────────

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
  pollingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: '#E3F2FD',
    borderRadius: 12,
    padding: 16,
  },
  pollingText: { color: '#1565C0', fontSize: 15, fontWeight: '600' },

  // Analysis error card
  analysisErrorCard: {
    backgroundColor: '#FFEBEE',
    marginHorizontal: 16,
    marginTop: 8,
    marginBottom: 4,
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 4,
    borderLeftColor: '#C62828',
  },
  analysisErrorTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#C62828',
    marginBottom: 6,
  },
  analysisErrorMsg: {
    fontSize: 13,
    color: '#B71C1C',
    lineHeight: 19,
    marginBottom: 10,
  },
  analysisErrorDismiss: {
    fontSize: 13,
    fontWeight: '600',
    color: '#C62828',
    textDecorationLine: 'underline',
  },

  // Analysis card
  analysisCard: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginBottom: 8,
    marginTop: 8,
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 4,
    borderLeftColor: '#1565C0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  analysisTitleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  modelBadge: {
    fontSize: 10,
    color: '#78909C',
    backgroundColor: '#F5F7FA',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  confidenceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
    gap: 8,
  },
  confidenceBar: {
    flex: 1,
    height: 6,
    backgroundColor: '#ECEFF1',
    borderRadius: 3,
    overflow: 'hidden',
  },
  confidenceFill: {
    height: '100%',
    borderRadius: 3,
  },
  subSection: {
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#ECEFF1',
  },
  subSectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: '#546E7A',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 10,
  },
  materialRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F5F7FA',
  },
  materialName: { fontSize: 14, fontWeight: '600', color: '#212121' },
  materialDetail: { fontSize: 12, color: '#78909C', marginTop: 2 },
  materialTotal: { fontSize: 14, fontWeight: '700', color: '#1565C0' },
  materialSumRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: 10,
  },
  materialSumLabel: { fontSize: 14, fontWeight: '700', color: '#212121' },
  materialSumValue: { fontSize: 14, fontWeight: '700', color: '#2E7D32' },
  stepRow: {
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F5F7FA',
  },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#1565C0',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  stepNumberText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  stepName: { fontSize: 14, fontWeight: '600', color: '#212121' },
  stepDesc: { fontSize: 12, color: '#78909C', marginTop: 2, lineHeight: 17 },
  stepHours: { fontSize: 12, color: '#1565C0', marginTop: 4, fontWeight: '600' },
});
