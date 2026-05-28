const form = document.querySelector("#reportForm");
const formStatus = document.querySelector("#formStatus");
const driversList = document.querySelector("#driversList");
const alertsList = document.querySelector("#alertsList");
const reportsList = document.querySelector("#reportsList");
const rewardButton = document.querySelector("#rewardButton");

const api = {
  drivers: "/api/drivers",
  reports: "/api/reports",
  alerts: "/api/alerts",
  rewards: "/api/rewards/run",
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

async function refreshDashboard() {
  await Promise.all([loadDrivers(), loadReports(), loadAlerts()]);
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
      ? `Report ${report.id} submitted and manager SMS alert queued.`
      : `Report ${report.id} submitted.`;

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

refreshDashboard();
