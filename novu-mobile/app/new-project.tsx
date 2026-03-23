import { useState, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  Image,
  FlatList,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { ProjectsApi, PhotosApi } from '../src/services/api';
import { PROPERTY_TYPES, REPAIR_SCOPES } from '../src/types';

interface PickedPhoto {
  uri: string;
  filename: string;
}

export default function NewProjectScreen() {
  const router = useRouter();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [propertyType, setPropertyType] = useState('');
  const [repairScope, setRepairScope] = useState('');
  const [addressLabel, setAddressLabel] = useState('');
  const [locationLat, setLocationLat] = useState<number | undefined>();
  const [locationLng, setLocationLng] = useState<number | undefined>();
  const [photos, setPhotos] = useState<PickedPhoto[]>([]);

  const [loadingLocation, setLoadingLocation] = useState(false);
  const [saving, setSaving] = useState(false);

  // ── GPS ──────────────────────────────────────────────────────────────────
  const handleGetLocation = useCallback(async () => {
    setLoadingLocation(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Přístup odepřen', 'Povolte přístup k poloze v nastavení aplikace.');
        return;
      }
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setLocationLat(loc.coords.latitude);
      setLocationLng(loc.coords.longitude);

      // Reverse geocode
      const [geo] = await Location.reverseGeocodeAsync({
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude,
      });
      if (geo) {
        const parts = [geo.street, geo.streetNumber, geo.city].filter(Boolean);
        setAddressLabel(parts.join(' '));
      }
    } catch {
      Alert.alert('Chyba', 'Nepodařilo se získat polohu.');
    } finally {
      setLoadingLocation(false);
    }
  }, []);

  // ── Fotky ─────────────────────────────────────────────────────────────────
  const handlePickPhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Přístup odepřen', 'Povolte přístup k fotkám v nastavení aplikace.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      quality: 0.8,
    });
    if (!result.canceled) {
      const picked = result.assets.map((a) => ({
        uri: a.uri,
        filename: a.fileName ?? `photo_${Date.now()}.jpg`,
      }));
      setPhotos((prev) => [...prev, ...picked]);
    }
  }, []);

  const handleTakePhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Přístup odepřen', 'Povolte přístup ke kameře v nastavení aplikace.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      quality: 0.8,
    });
    if (!result.canceled) {
      const a = result.assets[0];
      setPhotos((prev) => [
        ...prev,
        { uri: a.uri, filename: a.fileName ?? `photo_${Date.now()}.jpg` },
      ]);
    }
  }, []);

  const removePhoto = useCallback((uri: string) => {
    setPhotos((prev) => prev.filter((p) => p.uri !== uri));
  }, []);

  // ── Uložit ────────────────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    if (!title.trim()) {
      Alert.alert('Chyba', 'Vyplňte název zakázky.');
      return;
    }
    setSaving(true);
    try {
      const created = await ProjectsApi.create({
        title: title.trim(),
        description: description.trim() || undefined,
        source: 'mobile',
        locationLat,
        locationLng,
        addressLabel: addressLabel.trim() || undefined,
        propertyType: propertyType || undefined,
        repairScope: repairScope || undefined,
      });

      // Upload photos
      if (photos.length > 0) {
        await Promise.allSettled(
          photos.map((p) => PhotosApi.upload(created.id, p.uri, p.filename)),
        );
      }

      Alert.alert('Hotovo', 'Zakázka byla vytvořena.', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Chyba při ukládání.';
      Alert.alert('Chyba', msg);
    } finally {
      setSaving(false);
    }
  }, [title, description, locationLat, locationLng, addressLabel, propertyType, repairScope, photos, router]);

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      {/* Název */}
      <Section title="Název zakázky *">
        <TextInput
          style={styles.input}
          value={title}
          onChangeText={setTitle}
          placeholder="Např. Oprava střechy Novák"
          placeholderTextColor="#90A4AE"
        />
      </Section>

      {/* Popis */}
      <Section title="Popis / poznámka">
        <TextInput
          style={[styles.input, styles.inputMultiline]}
          value={description}
          onChangeText={setDescription}
          placeholder="Stručný popis závady nebo požadavku…"
          placeholderTextColor="#90A4AE"
          multiline
          numberOfLines={3}
          textAlignVertical="top"
        />
      </Section>

      {/* Typ objektu */}
      <Section title="Typ objektu">
        <View style={styles.chipRow}>
          {PROPERTY_TYPES.map((t) => (
            <TouchableOpacity
              key={t.value}
              style={[styles.chip, propertyType === t.value && styles.chipActive]}
              onPress={() => setPropertyType(propertyType === t.value ? '' : t.value)}
            >
              <Text style={[styles.chipText, propertyType === t.value && styles.chipTextActive]}>
                {t.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </Section>

      {/* Rozsah opravy */}
      <Section title="Rozsah opravy">
        <View style={styles.chipRow}>
          {REPAIR_SCOPES.map((t) => (
            <TouchableOpacity
              key={t.value}
              style={[styles.chip, repairScope === t.value && styles.chipActive]}
              onPress={() => setRepairScope(repairScope === t.value ? '' : t.value)}
            >
              <Text style={[styles.chipText, repairScope === t.value && styles.chipTextActive]}>
                {t.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </Section>

      {/* Poloha */}
      <Section title="Poloha / adresa">
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={handleGetLocation}
          disabled={loadingLocation}
        >
          {loadingLocation ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.actionBtnText}>📍 Načíst moji polohu</Text>
          )}
        </TouchableOpacity>
        <TextInput
          style={[styles.input, { marginTop: 8 }]}
          value={addressLabel}
          onChangeText={setAddressLabel}
          placeholder="Adresa (vyplní se automaticky)"
          placeholderTextColor="#90A4AE"
        />
        {locationLat != null && (
          <Text style={styles.coordsText}>
            {locationLat.toFixed(5)}, {locationLng?.toFixed(5)}
          </Text>
        )}
      </Section>

      {/* Fotky */}
      <Section title={`Fotky (${photos.length})`}>
        <View style={styles.photoButtons}>
          <TouchableOpacity style={[styles.actionBtn, styles.photoBtn]} onPress={handleTakePhoto}>
            <Text style={styles.actionBtnText}>📷 Vyfotit</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.actionBtn, styles.photoBtn, styles.actionBtnOutline]} onPress={handlePickPhoto}>
            <Text style={[styles.actionBtnText, styles.actionBtnTextOutline]}>🖼 Z galerie</Text>
          </TouchableOpacity>
        </View>
        {photos.length > 0 && (
          <FlatList
            horizontal
            data={photos}
            keyExtractor={(item) => item.uri}
            renderItem={({ item }) => (
              <View style={styles.photoThumbContainer}>
                <Image source={{ uri: item.uri }} style={styles.photoThumb} />
                <TouchableOpacity
                  style={styles.photoRemove}
                  onPress={() => removePhoto(item.uri)}
                >
                  <Text style={styles.photoRemoveText}>✕</Text>
                </TouchableOpacity>
              </View>
            )}
            style={{ marginTop: 10 }}
            contentContainerStyle={{ gap: 8 }}
          />
        )}
      </Section>

      {/* Uložit */}
      <View style={styles.saveRow}>
        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveBtnText}>Vytvořit zakázku</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Bottom padding */}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F5F7FA' },
  section: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 1,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#546E7A',
    marginBottom: 10,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  input: {
    borderWidth: 1.5,
    borderColor: '#CFD8DC',
    borderRadius: 10,
    padding: 12,
    fontSize: 15,
    color: '#212121',
    backgroundColor: '#FAFAFA',
  },
  inputMultiline: { minHeight: 80 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    borderWidth: 1.5,
    borderColor: '#CFD8DC',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  chipActive: { borderColor: '#1565C0', backgroundColor: '#E3F2FD' },
  chipText: { fontSize: 13, color: '#546E7A' },
  chipTextActive: { color: '#1565C0', fontWeight: '700' },
  actionBtn: {
    backgroundColor: '#1565C0',
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
  },
  actionBtnOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: '#1565C0',
  },
  actionBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  actionBtnTextOutline: { color: '#1565C0' },
  coordsText: { color: '#90A4AE', fontSize: 12, marginTop: 6, textAlign: 'center' },
  photoButtons: { flexDirection: 'row', gap: 10 },
  photoBtn: { flex: 1 },
  photoThumbContainer: { position: 'relative' },
  photoThumb: { width: 80, height: 80, borderRadius: 8 },
  photoRemove: {
    position: 'absolute',
    top: -6,
    right: -6,
    backgroundColor: '#C62828',
    width: 22,
    height: 22,
    borderRadius: 11,
    justifyContent: 'center',
    alignItems: 'center',
  },
  photoRemoveText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  saveRow: { marginHorizontal: 16, marginTop: 20 },
  saveBtn: {
    backgroundColor: '#2E7D32',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
