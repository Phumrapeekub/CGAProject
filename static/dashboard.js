function pad(n){ return String(n).padStart(2,'0'); }
function fmt(d){
  const m = ["ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.","ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."];
  return `${pad(d.getDate())} ${m[d.getMonth()]} ${d.getFullYear()+543}`;
}
function startWeekMon(date){
  const d = new Date(date);
  const day = (d.getDay()+6)%7;
  d.setDate(d.getDate()-day);
  d.setHours(0,0,0,0);
  return d;
}
function endWeekMon(date){
  const s = startWeekMon(date);
  const e = new Date(s);
  e.setDate(e.getDate()+6);
  e.setHours(23,59,59,999);
  return e;
}
function startMonth(date){ const d=new Date(date.getFullYear(), date.getMonth(), 1); d.setHours(0,0,0,0); return d; }
function endMonth(date){ const d=new Date(date.getFullYear(), date.getMonth()+1, 0); d.setHours(23,59,59,999); return d; }

document.addEventListener("DOMContentLoaded", () => {
  const now = new Date();

  const elToday = document.getElementById("range-today");
  const elWeek = document.getElementById("range-week");
  const elMonth = document.getElementById("range-month");

  if (elToday) elToday.textContent = fmt(now);
  const ws = startWeekMon(now), we = endWeekMon(now);
  if (elWeek) elWeek.textContent = `${fmt(ws)} - ${fmt(we)}`;
  const ms = startMonth(now), me = endMonth(now);
  if (elMonth) elMonth.textContent = `${fmt(ms)} - ${fmt(me)}`;
});
