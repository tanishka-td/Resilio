const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const colors = { orange: '#ff4e2d', cream: '#9c9d95', grey: '#8a8e87', green: '#b7d98d', dark: false };

let catalog = [];
let selectedSku = '';
let selectedWarehouse = '';
let busy = false;

function text(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value;
}

function number(value, digits = 0) {
  return new Intl.NumberFormat('en', { maximumFractionDigits: digits }).format(value);
}

function setApiState(online, label) {
  const status = $('#api-status');
  if (!status) return;
  status.textContent = label;
  status.parentElement.classList.toggle('is-offline', !online);
}

function fillChoices() {
  const skus = [...new Set(catalog.map((item) => item.sku_id))].sort();
  const warehouses = [...new Set(catalog.map((item) => item.warehouse_id))].sort();
  $$('.sku-select').forEach((select) => {
    select.replaceChildren(...skus.map((sku) => new Option(sku, sku)));
    select.value = selectedSku;
  });
  $$('.warehouse-select').forEach((select) => {
    select.replaceChildren(...warehouses.map((warehouse) => new Option(warehouse, warehouse)));
    select.value = selectedWarehouse;
  });
}

function choosePair(source) {
  if (source.classList.contains('sku-select')) selectedSku = source.value;
  if (source.classList.contains('warehouse-select')) selectedWarehouse = source.value;
  const pairExists = catalog.some((item) => item.sku_id === selectedSku && item.warehouse_id === selectedWarehouse);
  if (!pairExists) {
    const replacement = catalog.find((item) => item.sku_id === selectedSku) || catalog[0];
    selectedSku = replacement.sku_id;
    selectedWarehouse = replacement.warehouse_id;
  }
  $$('.sku-select').forEach((select) => { select.value = selectedSku; });
  $$('.warehouse-select').forEach((select) => { select.value = selectedWarehouse; });
  refreshSelectedSeries();
}

function escapeXml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[char]);
}

function chartTick(value) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.slice(5).replace('-', '/');
  return value;
}

function renderLineChart(container, labels, series, options = {}) {
  if (!container || !labels.length) return;
  const width = 900;
  const height = options.height || 300;
  const pad = { left: 54, right: 16, top: 17, bottom: 37 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const allValues = series.flatMap((line) => line.values.filter(Number.isFinite));
  const ceiling = Math.max(1, ...allValues);
  const floor = Math.min(0, ...allValues);
  const span = Math.max(1, ceiling - floor);
  const x = (index) => pad.left + (labels.length < 2 ? plotWidth / 2 : (index / (labels.length - 1)) * plotWidth);
  const y = (value) => pad.top + ((ceiling - value) / span) * plotHeight;
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = ceiling - (span * index) / 4;
    const yy = pad.top + (plotHeight * index) / 4;
    return `<g><line class="chart-grid" x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}"/><text class="chart-axis" x="${pad.left - 9}" y="${yy + 3}" text-anchor="end">${number(value, value < 10 ? 1 : 0)}</text></g>`;
  }).join('');
  const tickIndexes = [...new Set([0, Math.round((labels.length - 1) / 4), Math.round((labels.length - 1) / 2), Math.round(3 * (labels.length - 1) / 4), labels.length - 1])];
  const xTicks = tickIndexes.map((index) => `<text class="chart-axis" x="${x(index)}" y="${height - 10}" text-anchor="${index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'}">${escapeXml(chartTick(labels[index]))}</text>`).join('');
  const paths = series.map((line) => {
    let segments = [];
    let active = [];
    line.values.forEach((value, index) => {
      if (Number.isFinite(value)) active.push(`${active.length ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`);
      else if (active.length) { segments.push(active.join(' ')); active = []; }
    });
    if (active.length) segments.push(active.join(' '));
    return segments.map((path) => `<path class="chart-line" d="${path}" stroke="${line.color}" stroke-width="${line.width || 3}"/>`).join('');
  }).join('');
  container.innerHTML = `<svg class="chart-svg${options.dark ? ' chart-svg-dark' : ''}" viewBox="0 0 ${width} ${height}" role="presentation" aria-hidden="true">${grid}${xTicks}${paths}</svg>`;
  container.querySelectorAll('.chart-line').forEach((path) => {
    const length = path.getTotalLength();
    path.style.setProperty('--line-length', `${length}px`);
  });
}

function renderBars(container, rows, labelKey, valueKey) {
  if (!container) return;
  const max = Math.max(1, ...rows.map((item) => item[valueKey]));
  container.replaceChildren(...rows.map((item, index) => {
    const row = document.createElement('div');
    row.className = 'bar-row';
    const label = document.createElement('span');
    label.textContent = item[labelKey];
    const track = document.createElement('span');
    track.className = 'bar-track';
    const fill = document.createElement('i');
    fill.className = 'bar-fill';
    fill.style.width = `${Math.max(1, (item[valueKey] / max) * 100)}%`;
    fill.style.animationDelay = `${index * 45}ms`;
    track.append(fill);
    const value = document.createElement('span');
    value.className = 'bar-value';
    value.textContent = number(item[valueKey]);
    row.append(label, track, value);
    return row;
  }));
}

function renderOverview(data) {
  text('#stat-rows', number(data.rows));
  text('#stat-skus', number(data.sku_count));
  text('#stat-warehouses', number(data.warehouse_count));
  text('#stat-dates', `${data.date_start.slice(0, 4)} — ${data.date_end.slice(0, 4)}`);
  text('#stat-suppliers', `${number(data.supplier_count || 0)} suppliers listed`);
  renderLineChart($('#monthly-chart'), data.monthly_sales.map((item) => item.month), [
    { name: 'Recorded sales', values: data.monthly_sales.map((item) => item.units), color: colors.orange },
  ], { height: 285 });
  renderBars($('#warehouse-chart'), data.warehouse_sales, 'warehouse_id', 'units');
  renderBars($('#sku-chart'), data.top_skus, 'sku_id', 'units');
}

async function refreshSelectedSeries() {
  if (!selectedSku || !selectedWarehouse) return;
  text('#forecast-selection', `${selectedSku} / ${selectedWarehouse}`);
  try {
    const [history, forecast] = await Promise.all([
      ResilioAPI.history(selectedSku, selectedWarehouse),
      ResilioAPI.forecast(selectedSku, selectedWarehouse),
    ]);
    const recent = history.history.slice(-42);
    const dates = recent.map((item) => item.date);
    renderLineChart($('#history-chart'), dates, [
      { name: 'Recorded sales', values: recent.map((item) => item.units_sold), color: '#ff4e2d' },
    ], { height: 240 });
    text('#history-range', `${dates[0]} — ${dates.at(-1)} / daily recorded sales`);
    const predicted = forecast.forecast;
    const forecastDates = [...dates, ...predicted.map((item) => item.date)];
    const actualValues = [...recent.map((item) => item.units_sold), ...predicted.map(() => null)];
    const predictedValues = [...recent.map(() => null)];
    predictedValues[predictedValues.length - 1] = recent.at(-1).units_sold;
    predictedValues.push(...predicted.map((item) => item.forecast_units));
    renderLineChart($('#forecast-chart'), forecastDates, [
      { name: 'Recorded sales', values: actualValues, color: colors.cream, width: 2.5 },
      { name: 'Forecast', values: predictedValues, color: colors.orange, width: 3.5 },
    ], { height: 345 });
    text('#forecast-meta', `Through ${forecast.trained_through} · ${forecast.lead_time_days}-day listed lead time · promotions excluded`);
    text('#forecast-through', `MODEL TRAINED THROUGH ${forecast.trained_through}`);
  } catch (error) {
    text('#history-range', error.message);
    text('#forecast-meta', 'Forecast unavailable until the local API is ready.');
  }
}

function renderScenario(result) {
  const normal = result.comparisons.normal_conditions;
  const disrupted = result.comparisons.selected_disruption;
  const response = result.comparisons.disruption_with_response;
  const dates = normal.daily.map((item) => item.date);
  renderLineChart($('#simulation-chart'), dates, [
    { name: 'Normal', values: normal.daily.map((item) => item.ending_stock_units), color: colors.grey, width: 2.5 },
    { name: 'Disruption', values: disrupted.daily.map((item) => item.ending_stock_units), color: colors.orange, width: 3.5 },
    { name: 'With response', values: response.daily.map((item) => item.ending_stock_units), color: colors.green, width: 3 },
  ], { height: 310, dark: true });
  text('#scenario-state', 'COMPARISON READY');
  text('#scenario-horizon', `${dates.length} DAYS`);
  const makeMetric = (label, index, summary, variant) => {
    const card = document.createElement('div');
    card.className = `scenario-metric ${variant}`;
    const numberLabel = document.createElement('span');
    numberLabel.textContent = index;
    const title = document.createElement('p');
    title.textContent = label;
    const value = document.createElement('strong');
    value.textContent = number(summary[label === 'Shortage days' ? 'shortage_days' : label === 'Unmet demand' ? 'unmet_demand_units' : 'ending_stock_units'], 1);
    const note = document.createElement('small');
    note.textContent = label === 'Shortage days' && summary.first_shortage_date ? `First: ${summary.first_shortage_date}` : 'units / simulated';
    card.append(numberLabel, title, value, note);
    return card;
  };
  const metrics = $('#scenario-metrics');
  metrics.replaceChildren(
    makeMetric('Shortage days', '01 / DISRUPTION', disrupted.summary, 'is-disruption'),
    makeMetric('Unmet demand', '02 / DISRUPTION', disrupted.summary, 'is-disruption'),
    makeMetric('Ending stock', '03 / RESPONSE', response.summary, 'is-response'),
  );
}

async function submitScenario(event) {
  event.preventDefault();
  if (busy) return;
  const form = event.currentTarget;
  const data = new FormData(form);
  const inputs = Object.fromEntries(['opening_stock', 'order_units', 'demand_multiplier', 'delay_days', 'shipment_loss_fraction', 'extra_stock_units', 'expedite_days'].map((key) => [key, Number(data.get(key))]));
  inputs.sku_id = $('#sim-sku').value;
  inputs.warehouse_id = $('#sim-warehouse').value;
  if (!Number.isFinite(inputs.opening_stock) || !Number.isFinite(inputs.order_units)) {
    text('#sim-message', 'Enter a starting stock and planned order size first.');
    return;
  }
  busy = true;
  const button = $('.submit-scenario');
  button.disabled = true;
  button.querySelector('span').textContent = 'CALCULATING…';
  const message = $('#sim-message');
  message.classList.remove('is-error');
  message.textContent = 'Projecting demand and rolling inventory forward…';
  try {
    const result = await ResilioAPI.simulate(inputs);
    renderScenario(result);
    message.textContent = 'Scenario calculated from your inputs and the model forecast.';
  } catch (error) {
    message.textContent = error.message;
    message.classList.add('is-error');
    text('#scenario-state', 'CHECK INPUTS');
  } finally {
    busy = false;
    button.disabled = false;
    button.querySelector('span').textContent = 'RUN SCENARIO';
  }
}

function setupNavigation() {
  const links = $$('.nav-link');
  const sections = links.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    links.forEach((link) => {
      const active = link.hash === `#${visible.target.id}`;
      link.classList.toggle('is-active', active);
      if (active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }, { rootMargin: '-25% 0px -60% 0px', threshold: [0, .15, .4] });
  sections.forEach((section) => observer.observe(section));

  const menuButton = $('.menu-toggle');
  const mobileNav = $('#mobile-nav');
  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    mobileNav.hidden = !open;
  });
  mobileNav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
    mobileNav.hidden = true;
    menuButton.setAttribute('aria-expanded', 'false');
  }));
}

function setupReveals() {
  if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    $$('.reveal').forEach((item) => item.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }), { threshold: .08 });
  $$('.reveal').forEach((item) => observer.observe(item));
}

async function init() {
  setupNavigation();
  setupReveals();
  $('#simulation-form').addEventListener('submit', submitScenario);
  $('#demand-display').textContent = `${Number($('[name="demand_multiplier"]').value).toFixed(2)}×`;
  $('[name="demand_multiplier"]').addEventListener('input', (event) => {
    $('#demand-display').textContent = `${Number(event.target.value).toFixed(2)}×`;
  });
  $$('.sku-select, .warehouse-select').forEach((select) => select.addEventListener('change', () => choosePair(select)));

  try {
    const [health, items, overview] = await Promise.all([ResilioAPI.health(), ResilioAPI.items(), ResilioAPI.overview()]);
    catalog = items.items;
    if (!catalog.length) throw new Error('No SKU and warehouse pairs were found in the dataset.');
    selectedSku = catalog[0].sku_id;
    selectedWarehouse = catalog[0].warehouse_id;
    fillChoices();
    renderOverview(overview);
    setApiState(true, `MODEL ONLINE · DATA THROUGH ${health.data_through}`);
    text('#sim-message', 'Enter your stock and order assumptions to compare scenarios.');
    await refreshSelectedSeries();
  } catch (error) {
    setApiState(false, 'LOCAL MODEL OFFLINE');
    text('#sim-message', 'Start the local Python API to load demo charts and forecasts.');
    text('#forecast-selection', 'Local API not connected');
    console.info('Resilio data service is not available:', error.message);
  }
}

document.addEventListener('DOMContentLoaded', init);
