import { View, Text, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';

export default function ProfileScreen() {
  const { user, logout } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    Alert.alert('Odhlášení', 'Opravdu se chcete odhlásit?', [
      { text: 'Zrušit', style: 'cancel' },
      {
        text: 'Odhlásit',
        style: 'destructive',
        onPress: async () => {
          await logout();
          router.replace('/login');
        },
      },
    ]);
  }

  return (
    <View style={styles.container}>
      <View style={styles.avatarCircle}>
        <Text style={styles.avatarText}>
          {user?.fullName?.charAt(0)?.toUpperCase() ?? '?'}
        </Text>
      </View>

      <Text style={styles.name}>{user?.fullName ?? '—'}</Text>
      <Text style={styles.email}>{user?.email ?? '—'}</Text>

      <View style={styles.infoBox}>
        <InfoRow label="Role" value={user?.role ?? '—'} />
        <InfoRow label="Organizace" value={user?.organizationId ?? '—'} />
        {user?.isSuperAdmin && <InfoRow label="Super admin" value="Ano" />}
      </View>

      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Text style={styles.logoutText}>Odhlásit se</Text>
      </TouchableOpacity>
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
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
    alignItems: 'center',
    paddingTop: 40,
    paddingHorizontal: 24,
  },
  avatarCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#1565C0',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  avatarText: { color: '#fff', fontSize: 32, fontWeight: '700' },
  name: { fontSize: 20, fontWeight: '700', color: '#212121' },
  email: { fontSize: 14, color: '#546E7A', marginTop: 4, marginBottom: 24 },
  infoBox: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    width: '100%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.07,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 32,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  infoLabel: { color: '#78909C', fontSize: 14 },
  infoValue: { color: '#212121', fontSize: 14, fontWeight: '600' },
  logoutBtn: {
    backgroundColor: '#C62828',
    borderRadius: 12,
    paddingHorizontal: 32,
    paddingVertical: 14,
  },
  logoutText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
