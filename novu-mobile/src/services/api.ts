import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import type {
  LoginResponse,
  ProjectListResponse,
  ProjectCreate,
  ProjectCreateResponse,
  PhotoUploadResponse,
} from '../types';

const DEFAULT_BASE_URL = 'http://localhost:8000/api/v1';
const REQUEST_TIMEOUT_MS = 15_000;

export function getBaseUrl(): string {
  const extra = Constants.expoConfig?.extra as { apiUrl?: string } | undefined;
  return extra?.apiUrl ?? DEFAULT_BASE_URL;
}

const TOKEN_KEY = 'novu_access_token';
const REFRESH_KEY = 'novu_refresh_token';

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

async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await TokenStorage.getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const authHeaders = await getAuthHeaders();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...(options.headers as Record<string, string>),
      },
    });
  } catch (err: unknown) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Požadavek vypršel — zkontrolujte připojení k internetu.');
    }
    throw err;
  }
  clearTimeout(timer);

  if (!response.ok) {
    const body = await response.text();
    let message = `Chyba serveru (HTTP ${response.status})`;
    try {
      const json = JSON.parse(body);
      message = json.detail ?? json.message ?? message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const AuthApi = {
  async login(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async logout(refreshToken: string): Promise<void> {
    await request('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refreshToken }),
    }).catch(() => {
      // best-effort
    });
  },
};

export const ProjectsApi = {
  async list(params?: { status?: string; search?: string }): Promise<ProjectListResponse> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString() ? `?${qs}` : '';
    return request<ProjectListResponse>(`/cases${query}`);
  },

  async create(payload: ProjectCreate): Promise<ProjectCreateResponse> {
    return request<ProjectCreateResponse>('/cases', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};

export interface AnalysisJobStatus {
  id: string;
  status: string;
  errorMessage: string | null;
}

export const AnalysisApi = {
  async startJob(caseId: string): Promise<{ jobId: string }> {
    return request<{ jobId: string }>(`/cases/${caseId}/analysis-jobs`, { method: 'POST' });
  },

  async getJob(jobId: string): Promise<AnalysisJobStatus> {
    return request<AnalysisJobStatus>(`/analysis-jobs/${jobId}`);
  },
};

export const PhotosApi = {
  async upload(projectId: string, uri: string, filename: string): Promise<PhotoUploadResponse> {
    const token = await TokenStorage.getAccessToken();
    const formData = new FormData();
    formData.append('files', {
      uri,
      name: filename,
      type: 'image/jpeg',
    } as unknown as Blob);

    const response = await fetch(`${getBaseUrl()}/cases/${projectId}/images`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });

    if (!response.ok) {
      const body = await response.text();
      let message = `HTTP ${response.status}`;
      try {
        const json = JSON.parse(body);
        message = json.detail ?? json.message ?? message;
      } catch {
        // ignore
      }
      throw new Error(message);
    }

    return response.json() as Promise<PhotoUploadResponse>;
  },
};
