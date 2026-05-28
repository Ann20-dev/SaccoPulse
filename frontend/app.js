const form = document.querySelector("#reportForm");
const formStatus = document.querySelector("#formStatus");
const driversList = document.querySelector("#driversList");
const alertsList = document.querySelector("#alertsList");
const reportsList = document.querySelector("#reportsList");
const rewardButton = document.querySelector("#rewardButton");
const fetchSmsButton = document.querySelector("#fetchSmsButton");
const smsFetchStatus = document.querySelector("#smsFetchStatus");
const smsReportsList = document.querySelector("#smsReportsList");
const smsFilterButtons = document.querySelectorAll(".sms-filter");
let activeSmsStatus = "";

const api = {
  drivers: "/api/drivers",
  reports: "/api/reports",
  alerts: "/api/alerts",
  rewards: "/api/rewards/run",
  fetchSms: "/api/ats-sms/fetch",
  smsMessages: "/api/ats-sms/messages",
};

function titleCase(value) {
  return value
    .replaceAll("_", " ")
    .replace(/\w\S*/g, (text) => text.charAt(0).toUpperCase() + text.slice(1).toLowerCase());
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function scoreBadge(score) {
  if (score >= 85) return "good-score";
  if (score >= 70) return "medium";
  return "low-score";
}

function statusBadge(status) {
  if (status === "Actioned") return "good-score";
  if (status === "In Review") return "info";
  if (status === "Dismissed") return "low-score";
  return "medium";
}

function renderEmpty(container, message) {
  container.innerHTML = `<div class="item"><p class="meta">${message}</p></div>`;
}

async function loadDrivers() {
  const response = await fetch(api.drivers);
  const drivers = await response.json();

  driversList.innerHTML = drivers
    .map(
      (driver) => `
        <article class="item">
          <div>
            <strong>${driver.name}</strong>
            <span class="meta">${driver.route} | ${driver.vehicle_plate}</span>
          </div>
          <span class="badge ${scoreBadge(driver.score)}">${driver.score}/100</span>
          <span class="meta">${driver.reward_status}</span>
        </article>
      `
    )
    .join("");
}

async function loadReports() {
  const response = await fetch(api.reports);
  const reports = await response.json();

  if (!reports.length) {
    renderEmpty(reportsList, "No commuter reports yet.");
    return;
  }

  reportsList.innerHTML = reports
    .map(
      (report) => `
        <article class="item">
          <div>
            <strong>${titleCase(report.category)}</strong>
            <span class="meta">${report.route} | ${report.vehicle_plate}</span>
          </div>
          <span class="badge ${report.severity}">${titleCase(report.severity)}</span>
          <p class="meta">${report.description}</p>
          <span class="meta">Confirmation: ${report.confirmation_status}</span>
          <span class="meta">${formatDate(report.created_at)}</span>
        </article>
      `
    )
    .join("");
}

async function loadAlerts() {
  const response = await fetch(api.alerts);
  const alerts = await response.json();

  if (!alerts.length) {
    renderEmpty(alertsList, "No high-severity alerts yet.");
    return;
  }

  alertsList.innerHTML = alerts
    .map(
      (alert) => `
        <article class="item">
          <span class="badge high">SMS Alert</span>
          <strong>${alert.message}</strong>
          <span class="meta">Routed to manager ${alert.routed_to}</span>
          <span class="meta">${formatDate(alert.created_at)}</span>
        </article>
      `
    )
    .join("");
}

async function loadSmsReports() {
  const statusQuery = activeSmsStatus ? `?status=${encodeURIComponent(activeSmsStatus)}` : "";
  const response = await fetch(`${api.smsMessages}${statusQuery}`);
  const messages = await response.json();

  if (!messages.length) {
    renderEmpty(smsReportsList, "No fetched SMS reports match this status.");
    return;
  }

  smsReportsList.innerHTML = messages
    .map(
      (message) => `
        <article class="item">
          <div>
            <strong>${message.sender}</strong>
            <span class="meta">Africa's Talking ID: ${message.at_message_id}</span>
          </div>
          <span class="badge ${statusBadge(message.status)}">${message.status}</span>
          <p class="meta">${message.text}</p>
          <span class="meta">Received: ${message.received_at || "Not provided"}</span>
          <span class="meta">Fetched: ${formatDate(message.fetched_at)}</span>
          <div class="action-row">
            <button type="button" data-sms-id="${message.id}" data-next-status="In Review">Review</button>
            <button type="button" data-sms-id="${message.id}" data-next-status="Actioned">Actioned</button>
            <button type="button" data-sms-id="${message.id}" data-next-status="Dismissed">Dismiss</button>
          </div>
        </article>
      `
    )
    .join("");
}

async function refreshDashboard() {
  await Promise.all([loadDrivers(), loadReports(), loadAlerts(), loadSmsReports()]);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formStatus.textContent = "Submitting report...";

  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  const response = await fetch(api.reports, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    formStatus.textContent = "Report could not be submitted. Please check the fields.";
    return;
  }

  const report = await response.json();
  formStatus.textContent =
    report.severity === "high"
      ? `Report ${report.id} submitted. Confirmation and manager SMS queued.`
      : `Report ${report.id} submitted. Confirmation SMS queued.`;

  await refreshDashboard();
});

rewardButton.addEventListener("click", async () => {
  rewardButton.disabled = true;
  rewardButton.textContent = "Rewarding...";

  await fetch(api.rewards, { method: "POST" });
  await loadDrivers();

  rewardButton.disabled = false;
  rewardButton.textContent = "Run Airtime Rewards";
});

fetchSmsButton.addEventListener("click", async () => {
  fetchSmsButton.disabled = true;
  fetchSmsButton.textContent = "Fetching...";
  smsFetchStatus.textContent = "Fetching SMS reports from Africa's Talking...";

  const response = await fetch(api.fetchSms, { method: "POST" });
  const result = await response.json();

  if (!response.ok) {
    smsFetchStatus.textContent = result.detail || "Could not fetch SMS reports.";
  } else {
    smsFetchStatus.textContent = `Fetched ${result.fetched} messages, saved ${result.saved} new reports.`;
    await loadSmsReports();
  }

  fetchSmsButton.disabled = false;
  fetchSmsButton.textContent = "Fetch SMS Reports";
});

smsFilterButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    smsFilterButtons.forEach((filterButton) => filterButton.classList.remove("active"));
    button.classList.add("active");
    activeSmsStatus = button.dataset.status;
    await loadSmsReports();
  });
});

smsReportsList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-sms-id]");
  if (!button) return;

  button.disabled = true;
  await fetch(`${api.smsMessages}/${button.dataset.smsId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: button.dataset.nextStatus }),
  });
  await loadSmsReports();
});

refreshDashboard();
