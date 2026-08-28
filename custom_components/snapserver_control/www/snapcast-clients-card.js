function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function relativeTime(iso) {
  if (!iso) return "never";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "unknown";

  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

class SnapcastClientsCard extends HTMLElement {
  set hass(hass) {
    this._hass = hass;

    const state = hass.states[this._config?.entity];
    const clients = state?.attributes?.clients;
    const online = state?.attributes?.server_online;
    const json = JSON.stringify([clients, online]);

    if (json !== this._lastJson || !this._rendered) {
      this._lastJson = json;
      this._render();
    }
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define the Snapserver clients sensor entity");
    }
    this._config = {
      entity: config.entity,
      title: config.title || "Speakers",
      hide_disconnected: config.hide_disconnected || false,
      ...config,
    };
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig() {
    return { entity: "sensor.snapserver_clients_connected", title: "Speakers" };
  }

  disconnectedCallback() {
    this._stopTicking();
  }

  // "Last seen 3m ago" goes stale on its own, so re-render on a slow timer even
  // when no state change arrives.
  _startTicking() {
    if (this._timer) return;
    this._timer = window.setInterval(() => this._render(), 30000);
  }

  _stopTicking() {
    if (this._timer) {
      window.clearInterval(this._timer);
      this._timer = null;
    }
  }

  _render() {
    this._rendered = true;
    if (!this._hass || !this._config) return;

    const state = this._hass.states[this._config.entity];
    if (!state) {
      this.innerHTML = `<ha-card><div class="sc-empty">Entity not found: ${esc(
        this._config.entity
      )}</div></ha-card>`;
      return;
    }

    const all = state.attributes.clients || [];
    const clients = this._config.hide_disconnected
      ? all.filter((client) => client.connected)
      : all;
    const connectedCount = all.filter((client) => client.connected).length;
    const serverOnline = state.attributes.server_online !== false;

    const rows = clients
      .map((client) => {
        const detail = [client.ip, client.version ? `v${client.version}` : null]
          .filter(Boolean)
          .join(" · ");
        const status = client.connected
          ? "Connected"
          : `Last seen ${relativeTime(client.last_seen)}`;

        return `
        <div class="sc-client ${client.connected ? "" : "sc-down"}"
             data-entity="${esc(client.entity_id || "")}">
          <div class="sc-dot"></div>
          <div class="sc-info">
            <div class="sc-name">${esc(client.name) || "Unknown"}</div>
            <div class="sc-detail">${esc(detail)}</div>
          </div>
          <div class="sc-status">${esc(status)}</div>
        </div>`;
      })
      .join("");

    // A dead server makes every client look dead; say which it is.
    const banner = serverOnline
      ? ""
      : `<div class="sc-banner">Snapserver unreachable — client status may be stale</div>`;

    this.innerHTML = `
      <ha-card>
        <div class="sc-header">
          <span class="sc-title">${esc(this._config.title)}</span>
          <span class="sc-count">${connectedCount}/${all.length} up</span>
        </div>
        ${banner}
        <div class="sc-list">
          ${rows || '<div class="sc-empty">No Snapcast clients known</div>'}
        </div>
      </ha-card>
      <style>
        .sc-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px 4px;
        }
        .sc-title {
          font-size: 1.1em;
          font-weight: 500;
        }
        .sc-count {
          font-size: 0.85em;
          opacity: 0.7;
        }
        .sc-banner {
          margin: 4px 16px 0;
          padding: 6px 10px;
          border-radius: 4px;
          font-size: 0.85em;
          background: var(--warning-color, #ffa600);
          color: var(--text-primary-color, #fff);
        }
        .sc-list {
          padding: 4px 0 8px;
        }
        .sc-client {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px 16px;
          cursor: pointer;
          transition: background 0.2s;
        }
        .sc-client:hover {
          background: var(--secondary-background-color);
        }
        .sc-dot {
          width: 10px;
          height: 10px;
          min-width: 10px;
          border-radius: 50%;
          background: var(--success-color, #43a047);
        }
        .sc-down .sc-dot {
          background: var(--error-color, #db4437);
        }
        .sc-info {
          flex: 1;
          min-width: 0;
        }
        .sc-name {
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .sc-down .sc-name {
          opacity: 0.6;
        }
        .sc-detail {
          font-size: 0.8em;
          opacity: 0.6;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .sc-status {
          font-size: 0.85em;
          opacity: 0.7;
          text-align: right;
          white-space: nowrap;
        }
        .sc-down .sc-status {
          color: var(--error-color, #db4437);
          opacity: 1;
        }
        .sc-empty {
          padding: 16px;
          text-align: center;
          opacity: 0.6;
        }
      </style>
    `;

    this.querySelectorAll(".sc-client").forEach((row) => {
      row.addEventListener("click", () => {
        const entityId = row.getAttribute("data-entity");
        if (!entityId) return;
        this.dispatchEvent(
          new CustomEvent("hass-more-info", {
            detail: { entityId },
            bubbles: true,
            composed: true,
          })
        );
      });
    });

    this._startTicking();
  }
}

customElements.define("snapcast-clients-card", SnapcastClientsCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "snapcast-clients-card",
  name: "Snapcast Clients",
  description: "Shows which Snapcast clients are connected, and when the others were last seen.",
});
