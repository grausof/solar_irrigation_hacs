/**
 * solar-irrigation-card.js
 * Lovelace custom card for the Solar Irrigation integration.
 *
 * Config example:
 *   type: custom:solar-irrigation-card
 *   title: My Garden
 *   zones:
 *     - zone_id: zone_lawn
 *       name: Lawn
 *       color: "#4CAF50"
 *       factor_entity: sensor.solar_factor_zone_lawn
 *       deficit_entity: sensor.water_deficit_zone_lawn
 *       duration_entity: sensor.irrigation_duration_zone_lawn
 *       irrigate_entity: binary_sensor.should_irrigate_zone_lawn
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const CARD_CSS = `
  :host {
    display: block;
    font-family: var(--primary-font-family, Roboto, sans-serif);
  }
  ha-card {
    overflow: hidden;
  }
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 16px 0 16px;
  }
  .card-title {
    font-size: 1.1rem;
    font-weight: 500;
    color: var(--primary-text-color);
  }
  .card-subtitle {
    font-size: 0.75rem;
    color: var(--secondary-text-color);
  }
  .tabs {
    display: flex;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    margin: 12px 16px 0 16px;
  }
  .tab {
    padding: 8px 16px;
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--secondary-text-color);
    border-bottom: 2px solid transparent;
    transition: color 0.2s, border-color 0.2s;
    user-select: none;
  }
  .tab.active {
    color: var(--primary-color, #03a9f4);
    border-bottom-color: var(--primary-color, #03a9f4);
    font-weight: 500;
  }
  .tab-content {
    display: none;
    padding: 12px 16px 16px 16px;
  }
  .tab-content.active {
    display: block;
  }

  /* ── Zone status cards ── */
  .zone-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
  }
  .zone-card {
    border-radius: 8px;
    padding: 12px;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #e0e0e0);
    position: relative;
    overflow: hidden;
  }
  .zone-card::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: var(--zone-color, #4CAF50);
  }
  .zone-name {
    font-weight: 500;
    font-size: 0.95rem;
    color: var(--primary-text-color);
    margin-bottom: 8px;
    padding-left: 4px;
  }
  .zone-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    padding-left: 4px;
  }
  .stat {
    display: flex;
    flex-direction: column;
  }
  .stat-label {
    font-size: 0.68rem;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .stat-value {
    font-size: 1rem;
    font-weight: 500;
    color: var(--primary-text-color);
  }
  .stat-unit {
    font-size: 0.7rem;
    color: var(--secondary-text-color);
    font-weight: 400;
  }
  .irrigate-badge {
    display: inline-block;
    margin-top: 8px;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-left: 4px;
  }
  .irrigate-badge.on {
    background: rgba(3, 169, 244, 0.15);
    color: var(--info-color, #03a9f4);
  }
  .irrigate-badge.off {
    background: rgba(158, 158, 158, 0.15);
    color: var(--secondary-text-color);
  }
  .factor-bar-wrap {
    margin: 8px 4px 2px 4px;
    height: 6px;
    border-radius: 3px;
    background: var(--divider-color, #e0e0e0);
    overflow: hidden;
  }
  .factor-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.4s ease;
  }

  /* ── Monthly table ── */
  .month-table-wrap {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .month-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
    min-width: 540px;
  }
  .month-table th {
    padding: 6px 4px;
    text-align: center;
    color: var(--secondary-text-color);
    font-weight: 500;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    white-space: nowrap;
  }
  .month-table th.zone-col {
    text-align: left;
    padding-left: 8px;
    min-width: 100px;
  }
  .month-table td {
    padding: 6px 4px;
    text-align: center;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }
  .month-table td.zone-col {
    text-align: left;
    padding-left: 8px;
    font-weight: 500;
    color: var(--primary-text-color);
  }
  .month-table tr:last-child td {
    border-bottom: none;
  }
  .factor-cell {
    border-radius: 4px;
    padding: 3px 6px;
    display: inline-block;
    min-width: 36px;
    font-weight: 500;
    font-size: 0.78rem;
  }
  .month-col.current {
    background: rgba(var(--rgb-primary-color, 3,169,244), 0.08);
  }
  .unavailable {
    color: var(--secondary-text-color);
    font-style: italic;
    font-size: 0.85rem;
    padding: 16px 0;
    text-align: center;
  }
  .last-update {
    font-size: 0.7rem;
    color: var(--secondary-text-color);
    text-align: right;
    padding: 4px 0 0 0;
  }
`;

function factorColor(f) {
  // Green (full sun) → yellow → orange → red (full shadow)
  if (f === null || f === undefined) return '#9e9e9e';
  const v = Math.max(0, Math.min(1, f));
  if (v >= 0.7) return '#43a047'; // green
  if (v >= 0.5) return '#7cb342'; // light green
  if (v >= 0.35) return '#f9a825'; // amber
  if (v >= 0.2) return '#fb8c00'; // orange
  return '#e53935'; // red
}

function fmtFactor(v) {
  if (v === null || v === undefined || v === 'unavailable' || v === 'unknown') return '—';
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  return n.toFixed(2);
}

function fmtNum(v, decimals = 1) {
  if (v === null || v === undefined || v === 'unavailable' || v === 'unknown') return '—';
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  return n.toFixed(decimals);
}

class SolarIrrigationCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this._activeTab = 0;
    this._rendered = false;
  }

  setConfig(config) {
    if (!config.zones || !Array.isArray(config.zones) || config.zones.length === 0) {
      throw new Error('solar-irrigation-card: "zones" must be a non-empty array');
    }
    this._config = config;
    this._rendered = false;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _render() {
    const shadow = this.shadowRoot;
    shadow.innerHTML = '';

    const style = document.createElement('style');
    style.textContent = CARD_CSS;
    shadow.appendChild(style);

    const card = document.createElement('ha-card');

    // Header
    const header = document.createElement('div');
    header.className = 'card-header';
    const titleEl = document.createElement('div');
    titleEl.className = 'card-title';
    titleEl.textContent = this._config.title || 'Solar Irrigation';
    const subtitleEl = document.createElement('div');
    subtitleEl.className = 'card-subtitle';
    subtitleEl.id = 'si-subtitle';
    header.appendChild(titleEl);
    header.appendChild(subtitleEl);
    card.appendChild(header);

    // Tabs
    const tabs = document.createElement('div');
    tabs.className = 'tabs';
    const tabLabels = ['Zone Status', 'Monthly Factors'];
    tabLabels.forEach((label, i) => {
      const tab = document.createElement('div');
      tab.className = 'tab' + (i === this._activeTab ? ' active' : '');
      tab.textContent = label;
      tab.dataset.tab = i;
      tab.addEventListener('click', (e) => {
        this._activeTab = parseInt(e.currentTarget.dataset.tab);
        this._render();
        if (this._hass) this._update();
      });
      tabs.appendChild(tab);
    });
    card.appendChild(tabs);

    // Tab 0: Zone Status
    const tab0 = document.createElement('div');
    tab0.className = 'tab-content' + (this._activeTab === 0 ? ' active' : '');
    tab0.id = 'si-tab0';
    const zoneGrid = document.createElement('div');
    zoneGrid.className = 'zone-grid';
    zoneGrid.id = 'si-zone-grid';
    tab0.appendChild(zoneGrid);
    const lu0 = document.createElement('div');
    lu0.className = 'last-update';
    lu0.id = 'si-last-update-0';
    tab0.appendChild(lu0);
    card.appendChild(tab0);

    // Tab 1: Monthly Factors
    const tab1 = document.createElement('div');
    tab1.className = 'tab-content' + (this._activeTab === 1 ? ' active' : '');
    tab1.id = 'si-tab1';
    const tableWrap = document.createElement('div');
    tableWrap.className = 'month-table-wrap';
    tableWrap.id = 'si-table-wrap';
    tab1.appendChild(tableWrap);
    const lu1 = document.createElement('div');
    lu1.className = 'last-update';
    lu1.id = 'si-last-update-1';
    tab1.appendChild(lu1);
    card.appendChild(tab1);

    shadow.appendChild(card);
    this._rendered = true;
  }

  _update() {
    if (!this._rendered) this._render();
    if (!this._hass || !this._config) return;

    const now = new Date();
    const currentMonth = now.getMonth(); // 0-indexed

    const zones = this._config.zones;
    const stateFor = (entityId) => {
      if (!entityId) return null;
      return this._hass.states[entityId] || null;
    };

    // Update subtitle
    const subtitle = this.shadowRoot.getElementById('si-subtitle');
    if (subtitle) {
      subtitle.textContent = `${zones.length} zone${zones.length !== 1 ? 's' : ''}`;
    }

    // ── Tab 0: Zone Status ──
    const grid = this.shadowRoot.getElementById('si-zone-grid');
    if (grid) {
      grid.innerHTML = '';
      zones.forEach((zone) => {
        const factorState = stateFor(zone.factor_entity);
        const deficitState = stateFor(zone.deficit_entity);
        const durationState = stateFor(zone.duration_entity);
        const irrigateState = stateFor(zone.irrigate_entity);

        const factor = factorState ? parseFloat(factorState.state) : null;
        const deficit = deficitState ? parseFloat(deficitState.state) : null;
        const duration = durationState ? parseFloat(durationState.state) : null;
        const shouldIrrigate = irrigateState ? irrigateState.state === 'on' : null;

        const color = zone.color || '#4CAF50';
        const barColor = isNaN(factor) ? '#9e9e9e' : factorColor(factor);

        const card = document.createElement('div');
        card.className = 'zone-card';
        card.style.setProperty('--zone-color', color);

        card.innerHTML = `
          <div class="zone-name">${zone.name || zone.zone_id || 'Zone'}</div>
          <div class="zone-stats">
            <div class="stat">
              <span class="stat-label">Solar Factor</span>
              <span class="stat-value">${fmtFactor(factor)}</span>
            </div>
            <div class="stat">
              <span class="stat-label">Deficit</span>
              <span class="stat-value">${fmtNum(deficit)} <span class="stat-unit">mm</span></span>
            </div>
            <div class="stat">
              <span class="stat-label">Duration</span>
              <span class="stat-value">${fmtNum(duration)} <span class="stat-unit">min</span></span>
            </div>
            <div class="stat">
              <span class="stat-label">Irrigate</span>
              <span class="stat-value">${shouldIrrigate === null ? '—' : (shouldIrrigate ? 'Yes' : 'No')}</span>
            </div>
          </div>
          <div class="factor-bar-wrap">
            <div class="factor-bar" style="width:${isNaN(factor) ? 0 : Math.round(factor * 100)}%; background:${barColor};"></div>
          </div>
          ${shouldIrrigate !== null
            ? `<span class="irrigate-badge ${shouldIrrigate ? 'on' : 'off'}">${shouldIrrigate ? '💧 Needs water' : '✓ OK'}</span>`
            : ''}
        `;

        grid.appendChild(card);
      });
    }

    // ── Tab 1: Monthly Factors ──
    const tableWrap = this.shadowRoot.getElementById('si-table-wrap');
    if (tableWrap) {
      tableWrap.innerHTML = '';

      // Collect monthly_factors from factor entity attributes
      const hasData = zones.some((zone) => {
        const state = stateFor(zone.factor_entity);
        return state && state.attributes && Array.isArray(state.attributes.monthly_factors);
      });

      if (!hasData) {
        const msg = document.createElement('div');
        msg.className = 'unavailable';
        msg.textContent = 'Monthly factors not yet available. The integration may still be computing.';
        tableWrap.appendChild(msg);
      } else {
        const table = document.createElement('table');
        table.className = 'month-table';

        // Header row
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const thZone = document.createElement('th');
        thZone.className = 'zone-col';
        thZone.textContent = 'Zone';
        headerRow.appendChild(thZone);
        MONTHS.forEach((m, i) => {
          const th = document.createElement('th');
          th.className = 'month-col' + (i === currentMonth ? ' current' : '');
          th.textContent = m;
          headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Data rows
        const tbody = document.createElement('tbody');
        zones.forEach((zone) => {
          const state = stateFor(zone.factor_entity);
          const factors = state && state.attributes && Array.isArray(state.attributes.monthly_factors)
            ? state.attributes.monthly_factors
            : null;

          const row = document.createElement('tr');
          const tdName = document.createElement('td');
          tdName.className = 'zone-col';
          const dot = document.createElement('span');
          dot.style.cssText = `display:inline-block;width:8px;height:8px;border-radius:50%;background:${zone.color || '#4CAF50'};margin-right:6px;vertical-align:middle;`;
          tdName.appendChild(dot);
          tdName.appendChild(document.createTextNode(zone.name || zone.zone_id || 'Zone'));
          row.appendChild(tdName);

          for (let i = 0; i < 12; i++) {
            const td = document.createElement('td');
            td.className = 'month-col' + (i === currentMonth ? ' current' : '');
            if (factors && factors[i] !== undefined) {
              const val = parseFloat(factors[i]);
              const cell = document.createElement('span');
              cell.className = 'factor-cell';
              cell.style.cssText = `background:${factorColor(val)}22; color:${factorColor(val)};`;
              cell.textContent = val.toFixed(2);
              td.appendChild(cell);
            } else {
              td.textContent = '—';
            }
            row.appendChild(td);
          }
          tbody.appendChild(row);
        });
        table.appendChild(tbody);
        tableWrap.appendChild(table);
      }
    }

    // Last update timestamp
    const tsStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    ['si-last-update-0', 'si-last-update-1'].forEach((id) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.textContent = `Updated: ${tsStr}`;
    });
  }

  // Called by HA to get card size (in grid rows)
  getCardSize() {
    const zones = (this._config && this._config.zones) ? this._config.zones.length : 1;
    return 3 + Math.ceil(zones / 2);
  }

  // Static method for the card editor picker
  static getConfigElement() {
    return document.createElement('div'); // no visual editor yet
  }

  static getStubConfig() {
    return {
      title: 'Solar Irrigation',
      zones: [
        {
          zone_id: 'zone_lawn',
          name: 'Lawn',
          color: '#4CAF50',
          factor_entity: 'sensor.solar_factor_zone_lawn',
          deficit_entity: 'sensor.water_deficit_zone_lawn',
          duration_entity: 'sensor.irrigation_duration_zone_lawn',
          irrigate_entity: 'binary_sensor.should_irrigate_zone_lawn',
        },
      ],
    };
  }
}

customElements.define('solar-irrigation-card', SolarIrrigationCard);

// Register the card with the Lovelace card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-irrigation-card',
  name: 'Solar Irrigation Card',
  description: 'Displays zone shadow factors, water deficits, and monthly solar factor tables for the Solar Irrigation integration.',
  preview: false,
  documentationURL: 'https://github.com/yourusername/solar-irrigation-hacs',
});
