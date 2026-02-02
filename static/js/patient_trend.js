// static/js/patient_trend.js
(function () {
  // หา canvas
  const canvas = document.getElementById("trendChart");
  if (!canvas) return;

  // ดึงข้อมูลจาก data-* (มาจาก Jinja tojson)
  function parseJson(str, fallback) {
    try {
      return JSON.parse(str || "");
    } catch (e) {
      return fallback;
    }
  }

  const labels = parseJson(canvas.dataset.labels, []);
  const mmse   = parseJson(canvas.dataset.mmse, []);
  const tgds   = parseJson(canvas.dataset.tgds, []);
  const sra    = parseJson(canvas.dataset.sra, []);

  // ถ้าข้อมูลน้อยเกินไป ไม่ต้องสร้างกราฟ
  if (!Array.isArray(labels) || labels.length < 2) return;

  // ทำให้ทุก series ยาวเท่ากัน (กันข้อมูลขาด)
  const n = labels.length;
  const fixLen = (arr) => {
    if (!Array.isArray(arr)) return Array(n).fill(0);
    if (arr.length === n) return arr;
    if (arr.length > n) return arr.slice(0, n);
    // ถ้าสั้นกว่า เติม 0
    return arr.concat(Array(n - arr.length).fill(0));
  };

  const mmseFixed = fixLen(mmse);
  const tgdsFixed = fixLen(tgds);
  const sraFixed  = fixLen(sra);

  // สร้างกราฟ
  const ctx = canvas.getContext("2d");

  // ถ้ามีกราฟเดิมอยู่ (เช่น hot reload) ลบทิ้งก่อน
  if (window.__patientTrendChart) {
    try { window.__patientTrendChart.destroy(); } catch (e) {}
    window.__patientTrendChart = null;
  }

  window.__patientTrendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "MMSE (0-30)",
          data: mmseFixed,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 3,
        },
        {
          label: "TGDS-15 (0-15)",
          data: tgdsFixed,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 3,
        },
        {
          label: "SRA",
          data: sraFixed,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            // ทำ tooltip ให้อ่านง่าย
            label: function (ctx) {
              const label = ctx.dataset.label || "";
              const value = ctx.parsed.y ?? 0;
              return `${label}: ${value}`;
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
    },
  });
})();
