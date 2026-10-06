const API_ROOT = 'http://127.0.0.1:8000/api';

async function apiRequest(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

const ResilioAPI = {
  health: () => apiRequest('/health'),
  items: () => apiRequest('/items'),
  overview: () => apiRequest('/overview'),
  history: (sku, warehouse) => apiRequest(`/history?${new URLSearchParams({ sku_id: sku, warehouse_id: warehouse })}`),
  forecast: (sku, warehouse, horizon = 14) => apiRequest(`/forecast?${new URLSearchParams({ sku_id: sku, warehouse_id: warehouse, horizon })}`),
  simulate: (inputs) => apiRequest('/simulate', { method: 'POST', body: JSON.stringify(inputs) }),
};
