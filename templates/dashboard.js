(function () {
  const el = document.getElementById('chart-data');
  if (!el) return;
  let data = {};
  try { data = JSON.parse(el.textContent); } catch (e) { console.error(e); }

  const barCtx = document.getElementById('barChart');
  if (barCtx && window.Chart) {
    new Chart(barCtx, {
      type: 'bar',
      data: {
        labels: data.bar_labels || [],
        datasets: [{ label: 'ผู้ป่วยทั้งหมด', data: data.bar_values || [], borderWidth: 1 }]
      },
      options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    });
  }

  const pieCtx = document.getElementById('pieChart');
  if (pieCtx && window.Chart) {
    new Chart(pieCtx, {
      type: 'pie',
      data: {
        labels: ['ความเสี่ยงต่ำ', 'ความเสี่ยงปานกลาง', 'ความเสี่ยงสูง'],
        datasets: [{ data: [data?.risk?.low ?? 0, data?.risk?.mid ?? 0, data?.risk?.high ?? 0] }]
      },
      options: { responsive: true }
    });
  }
})();
