import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import type {
  AuthUser,
  LoginResponse,
  ProjectListResponse,
  ProjectCreate,
  ProjectCreateResponse,
  PhotoUploadResponse,
} from '../types';

const REQUEST_TIMEOUT_MS = 15_000;
const TOKEN_KEY = 'novu_access_token';
const REFRESH_KEY = 'novu_refresh_token';

export class ClientConfigurationError extends Error {}

type ExpoExtraConfig = {
  apiUrl?: string;
};

function normalizeBaseUrl(rawValue: string): string {
  const normalized = rawValue.trim().replace(/\/+$/, '');
  if (!normalized) {
    throw new ClientConfigurationError(
      'Mobilni klient vyzaduje explicitni expo.extra.apiUrl nebo EXPO_PUBLIC_API_URL. Implicitni localhost fallback neni podporovany.',
    );
  }
  if (!/^https?:\/\//i.test(normalized)) {
    throw new ClientConfigurationError('API URL musi zacinat http:// nebo https://.');
  }
  return normalized;
}

export function getBaseUrl(): string {
  const extra = Constants.expoConfig?.extra as ExpoExtraConfig | undefined;
  return normalizeBaseUrl(extra?.apiUrl ?? '');
}

export const TokenStorage = {
  async getAccessToken(): Promise<string | null> {
    return SecureStore.getItemAsync(TOKEN_KEY);
  },
  async getRefreshToken(): Promise<string | null> {
    return SecureStore.getItemAsync(REFRESH_KEY);
  },
  async setTokens(access: string, refresh: string): Promise<void> {
    await Promise.all([
      SecureStore.setItemAsync(TOKEN_KEY, access),
      SecureStore.setItemAsync(REFRESH_KEY, refresh),
    ]);
  },
  async clearTokens(): Promise<void> {
    await Promise.all([
      SecureStore.deleteItemAsync(TOKEN_KEY),
      SecureStore.deleteItemAsync(REFRESH_KEY),
    ]);
  },
};

function isAuthRefreshCandidate(path: string): boolean {
  return !path.startsWith('/auth/login') && !path.startsWith('/auth/refresh') && !path.startsWith('/auth/logout');
}

function buildJsonHeaders(
  authToken: string | null,
  headers?: HeadersInit,
): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(headers as Record<string, string> | undefined),
  };
}

async function fetchWithTimeout(url: string, options: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Pozadavek vyprsel - zkontrolujte pripojeni nebo API URL.');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function parseApiError(response: Response): Promise<Error> {
  const body = await response.text();
  let message = `Chyba serveru (HTTP ${response.status})`;
  try {
    const json = JSON.parse(body);
    message = json.detail ?? json.message ?? message;
  } catch {
    // ignore
  }
  return new Error(message);
}

async function refreshSessionTokens(): Promise<boolean> {
  const refreshToken = await TokenStorage.getRefreshToken();
  if (!refreshToken) {
    await TokenStorage.clearTokens();
    return false;
  }

  const response = await fetchWithTimeout(`${getBaseUrl()}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
  }).catch(async () => {
    return null;
  });

  if (!response || !response.ok) {
    await TokenStorage.clearTokens();
    return false;
  }

  const payload = (await response.json()) as LoginResponse;
  await TokenStorage.setTokens(payload.accessToken, payload.refreshToken);
  return true;
}

export async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  requestOptions: { allowAuthRefresh?: boolean } = {},
): Promise<T> {
  const allowAuthRefresh = requestOptions.allowAuthRefresh ?? true;
  const url = `${getBaseUrl()}${path}`;
  const accessToken = await TokenStorage.getAccessToken();
  let response = await fetchWithTimeout(url, {
    ...options,
    headers: buildJsonHeaders(accessToken, options.headers),
  });

  if (response.status === 401 && allowAuthRefresh && isAuthRefreshCandidate(path)) {
    const refreshed = await refreshSessionTokens();
    if (refreshed) {
      const rotatedToken = await TokenStorage.getAccessToken();
      response = await fetchWithTimeout(url, {
        ...options,
        headers: buildJsonHeaders(rotatedToken, options.headers),
      });
    }
  }

  if (!response.ok) {
    throw await parseApiError(response);
  }
  return response.json() as Promise<T>;
}

export const AuthApi = {
  async login(email: string, password: string): Promise<LoginResponse> {
    return requestJson<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }, { allowAuthRefresh: false });
  },

  async refresh(refreshToken: string): Promise<LoginResponse> {
    return requestJson<LoginResponse>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refreshToken }),
    }, { allowAuthRefresh: false });
  },

  async logout(refreshToken: string): Promise<void> {
    await requestJson('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refreshToken }),
    }).catch(() => {
      // best-effort revoke
    });
  },

  async me(): Promise<AuthUser> {
    return requestJson<AuthUser>('/auth/me');
  },

  async bootstrapSession(): Promise<AuthUser | null> {
    const accessToken = await TokenStorage.getAccessToken();
    const refreshToken = await TokenStorage.getRefreshToken();
    if (!accessToken || !refreshToken) {
      await TokenStorage.clearTokens();
      return null;
    }
    try {
      return await AuthApi.me();
    } catch (err: unknown) {
      if (err instanceof ClientConfigurationError) {
        throw err;
      }
      await TokenStorage.clearTokens();
      return null;
    }
  },
};

export const ProjectsApi = {
  async list(params?: { status?: string; search?: string }): Promise<ProjectListResponse> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString() ? `?${qs}` : '';
    return requestJson<ProjectListResponse>(`/cases${query}`);
  },

  async create(payload: ProjectCreate): Promise<ProjectCreateResponse> {
    return requestJson<ProjectCreateResponse>('/cases', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getDetail<T>(projectId: string): Promise<T> {
    return requestJson<T>(`/cases/${projectId}`);
  },
};

export interface AnalysisJobStatus {
  id: string;
  status: string;
  errorMessage: string | null;
}

export const AnalysisApi = {
  async startJob(caseId: string): Promise<{ jobId: string }> {
    return requestJson<{ jobId: string }>(`/cases/${caseId}/analysis-jobs`, { method: 'POST' });
  },

  async getJob(jobId: string): Promise<AnalysisJobStatus> {
    return requestJson<AnalysisJobStatus>(`/analysis-jobs/${jobId}`);
  },
};

export const PhotosApi = {
  async upload(projectId: string, uri: string, filename: string): Promise<PhotoUploadResponse> {
    const formData = new FormData();
    formData.append('files', {
      uri,
      name: filename,
      type: 'image/jpeg',
    } as unknown as Blob);

    const initialToken = await TokenStorage.getAccessToken();
    let response = await fetchWithTimeout(`${getBaseUrl()}/cases/${projectId}/images`, {
      method: 'POST',
      headers: initialToken ? { Authorization: `Bearer ${initialToken}` } : {},
      body: formData,
    });

    if (response.status === 401) {
      const refreshed = await refreshSessionTokens();
      if (refreshed) {
        const rotatedToken = await TokenStorage.getAccessToken();
        response = await fetchWithTimeout(`${getBaseUrl()}/cases/${projectId}/images`, {
          method: 'POST',
          headers: rotatedToken ? { Authorization: `Bearer ${rotatedToken}` } : {},
          body: formData,
        });
      }
    }

    if (!response.ok) {
      throw await parseApiError(response);
    }

    return response.json() as Promise<PhotoUploadResponse>;
  },
};
