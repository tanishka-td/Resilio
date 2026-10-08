const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const colors = { orange: '#ff4e2d', cream: '#9c9d95', grey: '#8a8e87', green: '#b7d98d', dark: false };

let catalog = [];
let selectedSku = '';
let selectedWarehouse = '';
let scenarioTimer = null;
let scenarioRevision = 0;

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
  queueScenarioUpdate();
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
  const events = (options.events || []).map((event, index) => {
    const eventIndex = labels.indexOf(event.date);
    if (eventIndex < 0) return '';
    const xx = x(eventIndex);
    const labelX = Math.min(width - pad.right - 5, Math.max(pad.left + 5, xx + 6));
    return `<g class="chart-event"><line x1="${xx}" x2="${xx}" y1="${pad.top}" y2="${height - pad.bottom}" stroke="${event.color || colors.orange}" stroke-dasharray="4 5"/><text class="chart-event-label" x="${labelX}" y="${pad.top + 11 + (index % 3) * 12}" fill="${event.color || colors.orange}">${escapeXml(event.label)}</text><title>${escapeXml(event.title || event.label)}</title></g>`;
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
    const paths = segments.map((path) => `<path class="chart-line" d="${path}" stroke="${line.color}" stroke-width="${line.width || 3}"/>`).join('');
    const points = line.values.map((value, index) => {
      if (!Number.isFinite(value)) return '';
      const title = `${line.name}: ${labels[index]} · ${number(value, 1)} units`;
      return `<circle class="chart-point" cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="4" fill="${line.color}"><title>${escapeXml(title)}</title></circle>`;
    }).join('');
    return paths + points;
  }).join('');
  container.innerHTML = `<svg class="chart-svg${options.dark ? ' chart-svg-dark' : ''}" viewBox="0 0 ${width} ${height}" role="presentation" aria-hidden="true">${grid}${events}${xTicks}${paths}</svg>`;
  container.querySelectorAll('.chart-line').forEach((path) => {
    const length = path.getTotalLength();
    path.style.setProperty('--line-length', `${length}px`);
  });
}

function renderBars(container, rows, labelKey, valueKey) {
  if (!container) return;
  const values = rows.map((item) => item[valueKey]);
  const max = Math.max(1, ...values);
  const min = Math.min(...values);
  const span = Math.max(1, max - min);
  container.replaceChildren(...rows.map((item, index) => {
    const row = document.createElement('div');
    row.className = 'bar-row';
    const label = document.createElement('span');
    label.textContent = item[labelKey];
    const track = document.createElement('span');
    track.className = 'bar-track';
    const fill = document.createElement('i');
    fill.className = 'bar-fill';
    fill.style.width = `${35 + ((item[valueKey] - min) / span) * 65}%`;
    fill.style.animationDelay = `${index * 45}ms`;
    track.append(fill);
    const value = document.createElement('span');
    value.className = 'bar-value';
    value.innerHTML = `<strong>${number(item[valueKey])}</strong><small>−${number(max - item[valueKey])} vs #1</small>`;
    row.append(label, track, value);
    return row;
  }));
}

function renderShare(container, rows) {
  if (!container) return;
  const total = rows.reduce((sum, row) => sum + row.units, 0);
  const radius = 63;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const palette = ['#ff4e2d', '#777a72', '#b7d98d', '#c6a57b', '#a8aaa2', '#c15d40'];
  const rings = rows.map((row, index) => {
    const share = total ? row.units / total : 0;
    const length = share * circumference;
    const ring = `<circle cx="96" cy="96" r="${radius}" fill="none" stroke="${palette[index % palette.length]}" stroke-width="22" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 96 96)"><title>${escapeXml(row.warehouse_id)} · ${number(row.units)} units · ${number(share * 100, 1)}%</title></circle>`;
    offset += length;
    return ring;
  }).join('');
  const legend = rows.map((row, index) => `<div class="share-legend-item"><i style="--share-color:${palette[index % palette.length]}"></i><span>${escapeXml(row.warehouse_id)}</span><strong>${number(total ? row.units / total * 100 : 0, 1)}%</strong></div>`).join('');
  container.innerHTML = `<div class="share-donut"><svg viewBox="0 0 192 192" aria-hidden="true">${rings}</svg><div><strong>${number(total / 1000000, 2)}M</strong><small>TOTAL UNITS</small></div></div><div class="share-legend">${legend}</div>`;
}

function renderHeatmap(container, columns, rows, rowLabel) {
  if (!container || !columns?.length || !rows?.length) return;
  const max = Math.max(1, ...rows.flatMap((row) => row.units));
  container.style.setProperty('--heat-columns', columns.length);
  const header = `<span class="heatmap-corner"></span>${columns.map((column) => `<span class="heatmap-heading">${escapeXml(column)}</span>`).join('')}`;
  let cellIndex = 0;
  const body = rows.map((row) => `<span class="heatmap-row-label">${escapeXml(row[rowLabel])}</span>${row.units.map((value, index) => {
    const intensity = value / max;
    const delay = cellIndex++ * 18;
    return `<span class="heatmap-cell${intensity > .58 ? ' is-bright' : ''}" style="--heat-intensity:${.08 + intensity * .84};--heat-delay:${delay}ms" title="${escapeXml(row[rowLabel])} · ${escapeXml(columns[index])} · ${number(value)} units">${number(value)}</span>`;
  }).join('')}`).join('');
  container.innerHTML = `<div class="heatmap-grid">${header}${body}</div><div class="heatmap-scale"><span>LOW</span><i></i><span>HIGH</span></div>`;
}

function renderDistribution(container, values) {
  if (!container || !values.length) return;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const binCount = 8;
  const domainMin = max === min ? Math.max(0, min - .5) : min;
  const domainMax = max === min ? max + .5 : max;
  const span = domainMax - domainMin || 1;
  const bins = Array.from({ length: binCount }, () => 0);
  values.forEach((value) => bins[Math.min(binCount - 1, Math.floor(((value - domainMin) / span) * binCount))]++);
  const peak = Math.max(...bins, 1);
  const columns = bins.map((count, index) => {
    const low = domainMin + (span * index) / binCount;
    const high = domainMin + (span * (index + 1)) / binCount;
    return `<div class="distribution-bin" title="${number(low, 1)}–${number(high, 1)} units · ${count} days"><b>${count}</b><i style="--bin-height:${Math.max(3, count / peak * 72)}%"></i><span>${number(low, 0)}</span></div>`;
  }).join('');
  container.innerHTML = `<div class="distribution-bars">${columns}</div><div class="distribution-summary"><strong>${number(values.length)}</strong><span>days</span><strong>${number(min, 1)}–${number(max, 1)}</strong><span>units / day</span></div>`;
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
  text('#warehouse-scale-note', `Broken scale · ${number(Math.min(...data.warehouse_sales.map((row) => row.units)))}–${number(Math.max(...data.warehouse_sales.map((row) => row.units)))} units`);
  text('#sku-scale-note', `Broken scale · ${number(Math.min(...data.top_skus.map((row) => row.units)))}–${number(Math.max(...data.top_skus.map((row) => row.units)))} units`);
  renderShare($('#warehouse-share-chart'), data.warehouse_sales);
  renderHeatmap($('#warehouse-monthly-chart'), data.warehouse_monthly?.months, data.warehouse_monthly?.rows, 'warehouse_id');
  renderHeatmap($('#sku-warehouse-chart'), data.sku_warehouse?.warehouses, data.sku_warehouse?.rows, 'sku_id');
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
    renderDistribution($('#sales-distribution-chart'), history.history.map((item) => item.units_sold));
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
    ], { height: 345, events: [{ date: dates.at(-1), label: 'FORECAST START' }] });
    text('#forecast-meta', `Through ${forecast.trained_through} · ${forecast.lead_time_days}-day listed lead time · promotions excluded`);
    text('#forecast-through', `MODEL TRAINED THROUGH ${forecast.trained_through}`);
  } catch (error) {
    text('#history-range', error.message);
    text('#forecast-meta', 'Forecast is unavailable while the data service is offline.');
  }
}

function renderScenario(result) {
  const normal = result.comparisons.normal_conditions;
  const disrupted = result.comparisons.selected_disruption;
  const response = result.comparisons.disruption_with_response;
  const dates = normal.daily.map((item) => item.date);
  const arrivalEvents = [
    { scenario: 'Normal', result: normal, color: colors.grey },
    { scenario: 'Disruption', result: disrupted, color: colors.orange },
    { scenario: 'Response', result: response, color: colors.green },
  ].filter((item) => item.result.summary.arrival_date).map((item) => ({
    date: item.result.summary.arrival_date,
    label: `${item.scenario.toUpperCase()} +${number(item.result.summary.received_units)}U`,
    title: `${item.scenario} order arrives · ${number(item.result.summary.received_units)} units`,
    color: item.color,
  }));
  renderLineChart($('#simulation-chart'), dates, [
    { name: 'Normal', values: normal.daily.map((item) => item.ending_stock_units), color: colors.grey, width: 2.5 },
    { name: 'Disruption', values: disrupted.daily.map((item) => item.ending_stock_units), color: colors.orange, width: 3.5 },
    { name: 'With response', values: response.daily.map((item) => item.ending_stock_units), color: colors.green, width: 3 },
  ], { height: 340, dark: true, events: arrivalEvents });
  text('#scenario-state', 'COMPARISON READY');
  text('#scenario-horizon', `${dates.length} DAYS`);
  text('#scenario-insight', describeScenario(disrupted.summary, response.summary));
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

function describeScenario(disruption, response) {
  const shortageReduction = Math.max(0, disruption.shortage_days - response.shortage_days);
  const unmetReduction = Math.max(0, disruption.unmet_demand_units - response.unmet_demand_units);
  if (disruption.shortage_days === 0) {
    return `No shortage is projected under the selected disruption. The response scenario ends with ${number(response.ending_stock_units, 1)} units.`;
  }
  if (shortageReduction || unmetReduction > 0.05) {
    const changes = [];
    if (unmetReduction > 0.05) changes.push(`${number(unmetReduction, 1)} fewer units of unmet demand`);
    if (shortageReduction) changes.push(`${shortageReduction} fewer shortage days`);
    return `The selected response reduces ${changes.join(' and ')} compared with the disruption alone.`;
  }
  return 'The selected response does not change the projected shortage for these assumptions. Try adjusting prepared stock or delivery timing.';
}

function resetScenarioResults(message) {
  const chart = $('#simulation-chart');
  const placeholder = document.createElement('div');
  placeholder.className = 'chart-loading';
  placeholder.textContent = message;
  chart.replaceChildren(placeholder);
  text('#scenario-state', 'AWAITING INPUT');
  text('#scenario-horizon', '— DAYS');
  text('#scenario-insight', 'Enter starting stock and order size to see how your choices affect the outcome.');
  const metrics = $('#scenario-metrics');
  metrics.replaceChildren(...[
    ['01', 'Shortage days'],
    ['02', 'Unmet demand'],
    ['03', 'Ending stock'],
  ].map(([index, label]) => {
    const card = document.createElement('div');
    card.className = 'metric-empty';
    const numberLabel = document.createElement('span');
    numberLabel.textContent = index;
    const title = document.createElement('p');
    title.textContent = label;
    const value = document.createElement('strong');
    value.textContent = '—';
    card.append(numberLabel, title, value);
    return card;
  }));
}

function queueScenarioUpdate() {
  const form = $('#simulation-form');
  const button = $('.submit-scenario');
  const message = $('#sim-message');
  const revision = ++scenarioRevision;
  clearTimeout(scenarioTimer);
  button.disabled = false;
  button.querySelector('span').textContent = 'RECALCULATE NOW';
  message.classList.remove('is-error');
  if (!form.checkValidity()) {
    resetScenarioResults('Complete the required starting stock and planned order fields to see the comparison.');
    text('#sim-message', 'Enter your starting stock and order size to preview a scenario.');
    return;
  }
  text('#scenario-state', 'UPDATING');
  text('#scenario-insight', 'Recalculating the comparison with your latest assumptions…');
  text('#sim-message', 'Updating as your assumptions change…');
  scenarioTimer = setTimeout(() => updateScenario(form, revision), 350);
}

async function updateScenario(form, revision) {
  const data = new FormData(form);
  const inputs = Object.fromEntries(['opening_stock', 'order_units', 'demand_multiplier', 'delay_days', 'extra_stock_units', 'expedite_days'].map((key) => [key, Number(data.get(key))]));
  inputs.shipment_loss_fraction = Number(data.get('shipment_loss_percent')) / 100;
  inputs.sku_id = $('#sim-sku').value;
  inputs.warehouse_id = $('#sim-warehouse').value;
  const button = $('.submit-scenario');
  button.disabled = true;
  button.querySelector('span').textContent = 'UPDATING…';
  const message = $('#sim-message');
  message.classList.remove('is-error');
  try {
    const result = await ResilioAPI.simulate(inputs);
    if (revision !== scenarioRevision) return;
    renderScenario(result);
    message.textContent = 'Comparison updated from your assumptions and the demand projection.';
  } catch (error) {
    if (revision !== scenarioRevision) return;
    resetScenarioResults('The comparison could not be updated. Check the assumptions and try again.');
    message.textContent = error.message;
    message.classList.add('is-error');
    text('#scenario-state', 'CHECK INPUTS');
  } finally {
    if (revision === scenarioRevision) {
      button.disabled = false;
      button.querySelector('span').textContent = 'RECALCULATE NOW';
    }
  }
}

function submitScenario(event) {
  event.preventDefault();
  clearTimeout(scenarioTimer);
  const revision = ++scenarioRevision;
  updateScenario(event.currentTarget, revision);
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
  $('#simulation-form').addEventListener('input', queueScenarioUpdate);
  $('#simulation-form').addEventListener('change', queueScenarioUpdate);
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
    setApiState(false, 'MODEL OFFLINE');
    text('#sim-message', 'The data service could not load the demo. Please try again later.');
    text('#forecast-selection', 'Data service not connected');
    console.info('Resilio data service is not available:', error.message);
  }
}

document.addEventListener('DOMContentLoaded', init);
