import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { ProjectsApi } from '../../src/services/api';
import type { ProjectSummary } from '../../src/types';
import { PROJECT_STATUS_LABELS } from '../../src/types';

const STATUS_COLOR: Record<string, string> = {
  new: '#1565C0',
  in_progress: '#E65100',
  draft: '#6A1B9A',
  ready: '#2E7D32',
  sent: '#00838F',
  archived: '#546E7A',
};

function ProjectCard({ item, onPress }: { item: ProjectSummary; onPress: () => void }) {
  const statusLabel = PROJECT_STATUS_LABELS[item.status] ?? item.status;
  const statusColor = STATUS_COLOR[item.status] ?? '#546E7A';

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardTitle} numberOfLines={1}>{item.title}</Text>
        <View style={[styles.badge, { backgroundColor: statusColor }]}>
          <Text style={styles.badgeText}>{statusLabel}</Text>
        </View>
      </View>

      {item.addressLabel ? (
        <Text style={styles.cardMeta}>📍 {item.addressLabel}</Text>
      ) : null}

      <View style={styles.cardFooter}>
        {item.photoCount > 0 && (
          <Text style={styles.cardStat}>📷 {item.photoCount}</Text>
        )}
        {item.estimatedAreaSqm != null && (
          <Text style={styles.cardStat}>📐 {item.estimatedAreaSqm.toFixed(1)} m²</Text>
        )}
        {item.latestQuoteTotal != null && (
          <Text style={styles.cardStat}>
            💰 {item.latestQuoteTotal.toLocaleString('cs-CZ')} Kč
          </Text>
        )}
        {item.createdByName && (
          <Text style={styles.cardStat}>👷 {item.createdByName}</Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

export default function ProjectsScreen() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async (searchTerm?: string) => {
    try {
      setError(null);
      const res = await ProjectsApi.list({ search: searchTerm });
      setProjects(res.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Chyba při načítání.');
    }
  }, []);

  useEffect(() => {
    fetchProjects().finally(() => setLoading(false));
  }, [fetchProjects]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchProjects(search);
    setRefreshing(false);
  }, [fetchProjects, search]);

  const onSearchSubmit = useCallback(() => {
    fetchProjects(search);
  }, [fetchProjects, search]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#1565C0" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.searchRow}>
        <TextInput
          style={styles.searchInput}
          value={search}
          onChangeText={setSearch}
          onSubmitEditing={onSearchSubmit}
          placeholder="Hledat zakázky…"
          placeholderTextColor="#90A4AE"
          returnKeyType="search"
          clearButtonMode="while-editing"
        />
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity onPress={() => fetchProjects(search)}>
            <Text style={styles.retryText}>Zkusit znovu</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={projects}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) =>
            <ProjectCard
              item={item}
              onPress={() => router.push(`/project/${item.id}`)}
            />
          }
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={['#1565C0']} />
          }
          contentContainerStyle={projects.length === 0 ? styles.emptyContainer : styles.listContent}
          ListEmptyComponent={
            <Text style={styles.emptyText}>Žádné zakázky.</Text>
          }
        />
      )}

      <TouchableOpacity
        style={styles.fab}
        onPress={() => router.push('/new-project')}
        activeOpacity={0.85}
      >
        <Text style={styles.fabText}>＋ Nová zakázka</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F5F7FA' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  searchRow: {
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#E0E0E0',
  },
  searchInput: {
    backgroundColor: '#F5F7FA',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#212121',
    borderWidth: 1,
    borderColor: '#CFD8DC',
  },
  listContent: { padding: 12 },
  emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 },
  emptyText: { color: '#90A4AE', fontSize: 16 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  cardTitle: { fontSize: 15, fontWeight: '700', color: '#212121', flex: 1, marginRight: 8 },
  badge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  cardMeta: { color: '#546E7A', fontSize: 13, marginBottom: 6 },
  cardFooter: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  cardStat: { color: '#78909C', fontSize: 12 },
  errorBox: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  errorText: { color: '#C62828', fontSize: 15, textAlign: 'center', marginBottom: 12 },
  retryText: { color: '#1565C0', fontSize: 15, fontWeight: '600' },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 20,
    backgroundColor: '#1565C0',
    borderRadius: 28,
    paddingHorizontal: 22,
    paddingVertical: 14,
    shadowColor: '#1565C0',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 8,
    elevation: 6,
  },
  fabText: { color: '#fff', fontSize: 15, fontWeight: '700' },
});
