import axios from 'axios';
import type { AxiosRequestConfig, AxiosError } from 'axios';
import { User } from 'oidc-client-ts';
import { getOidcStorageKey } from '@/lib/auth';

const AXIOS_INSTANCE = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Get user from storage (set by react-oidc-context)
// Uses sessionStorage to match auth.ts config (XSS protection)
const getUser = (): User | null => {
  try {
    const oidcStorage = sessionStorage.getItem(getOidcStorageKey());
    return oidcStorage ? User.fromStorageString(oidcStorage) : null;
  } catch {
    return null;
  }
};

// Add access token to requests
AXIOS_INSTANCE.interceptors.request.use((config) => {
  const user = getUser();
  if (user?.access_token) {
    config.headers.Authorization = `Bearer ${user.access_token}`;
  }
  return config;
});

// Handle 401 responses
AXIOS_INSTANCE.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Token expired - react-oidc-context will handle refresh
      // or redirect to login
      console.warn('Unauthorized request - token may have expired');
    }
    return Promise.reject(error);
  }
);

export const customInstance = <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig
): Promise<T> => {
  const source = axios.CancelToken.source();
  const promise = AXIOS_INSTANCE({
    ...config,
    ...options,
    cancelToken: source.token,
  }).then(({ data }) => data);

  // @ts-expect-error - Adding cancel method for TanStack Query
  promise.cancel = () => source.cancel('Query was cancelled');

  return promise;
};

export default customInstance;

// Export types for generated code
export type ErrorType<Error> = AxiosError<Error>;
export type BodyType<BodyData> = BodyData;
