import tkinter as tk
import customtkinter as ctk
import calendar
from datetime import datetime, date, timedelta
from patients_list import patientsListFrame
import matplotlib as mpl
mpl.rcParams["font.family"] = "Prompt"
mpl.rcParams["axes.unicode_minus"] = False

from tkcalendar import Calendar

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import matplotlib
import matplotlib
from matplotlib import rcParams

rcParams["font.family"] = "Tahoma"
rcParams["axes.unicode_minus"] = False

rcParams["font.family"] = "Prompt"
rcParams["axes.unicode_minus"] = False



PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
BG = "#F3F4F6"
FONT = "Prompt"


# =========================
# Dummy data (เปลี่ยนไปดึง db ทีหลัง)
# =========================
def get_dashboard_data():
    stats = {"all": 0, "today": 0, "month": 0, "year": 0}

    risk_labels = ["ปกติ", "เสี่ยง", "ผิดปกติ"]
    risk_values = [0, 0, 0]

    age_bins = ["60-64", "65-69", "70-74", "75-79", "80+"]
    male = [0, 0, 0, 0, 0]
    female = [0, 0, 0, 0, 0]

    months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย."]
    assessed = [68, 72, 76, 80, 85, 90]
    patients = [45, 48, 52, 55, 58, 61]

    bottom = {"avg_age": 0, "avg_assess_per_person": 0, "risk_rate": 0}
    return stats, (risk_labels, risk_values), (age_bins, male, female), (months, assessed, patients), bottom


# =========================
# Small UI helpers
# =========================
def pill(parent, text, fg="#E6F0FF", tc=PRIMARY):
    return ctk.CTkLabel(
        parent,
        text=text,
        fg_color=fg,
        text_color=tc,
        corner_radius=999,
        font=(FONT, 12, "bold"),
        padx=12,
        pady=6,
    )


def card(parent, radius=22):
    return ctk.CTkFrame(parent, fg_color="white", corner_radius=radius)


def _center_popup(popup, parent, w=360, h=380):
    popup.update_idletasks()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    x = px + (pw - w) // 2
    y = py + (ph - h) // 2
    popup.geometry(f"{w}x{h}+{x}+{y}")


def _thai_month_names():
    return ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def make_entry_with_icon(parent, placeholder, icon="📅", command=None, height=40):
    """
    ช่อง input + ปุ่มไอคอนอยู่ในช่อง (ด้านขวา)
    """
    wrap = ctk.CTkFrame(parent, fg_color="#F8FAFC", corner_radius=12)
    wrap.pack(fill="x", pady=(14, 10))

    entry = ctk.CTkEntry(
        wrap,
        placeholder_text=placeholder,
        height=height,
        fg_color="transparent",
        border_width=0,
        font=(FONT, 13),
    )
    entry.pack(fill="x", padx=(14, 48), pady=2)

    btn = ctk.CTkButton(
        wrap,
        text=icon,
        width=36,
        height=height - 8,
        fg_color="#E6F0FF",
        hover_color="#D6E7FF",
        text_color="#0f172a",
        corner_radius=10,
        command=command,
    )
    btn.place(relx=1.0, x=-10, rely=0.5, anchor="e")

    if command:
        entry.bind("<Button-1>", lambda e: command())

    return wrap, entry


# =========================
# Dashboard
# =========================
class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master, on_logout=None):
        super().__init__(master, fg_color=BG)
        self.on_logout = on_logout
        self.pack(fill="both", expand=True)

        self.stats, self.risk, self.age, self.trend, self.bottom = get_dashboard_data()
        self.filter_range = None

        self._build_topbar()
        self._build_scroll_area()
        self._build_content()
        self._start_clock()

    # ---------- Topbar ----------
    def _build_topbar(self):
        top = ctk.CTkFrame(self, height=72, corner_radius=0, fg_color="white")
        top.pack(fill="x")
        top.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=18, pady=12)

        logo = ctk.CTkFrame(left, width=44, height=44, corner_radius=999, fg_color="#E6F0FF")
        logo.pack(side="left")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="🏥", font=(FONT, 18)).pack(expand=True)

        tbox = ctk.CTkFrame(left, fg_color="transparent")
        tbox.pack(side="left", padx=12)
        ctk.CTkLabel(tbox, text="ระบบประเมินสุขภาพผู้สูงอายุ", font=(FONT, 16, "bold"), text_color=PRIMARY).pack(anchor="w")
        ctk.CTkLabel(tbox, text="คลินิกผู้สูงอายุ โรงพยาบาลพะเยา", font=(FONT, 12), text_color="#64748B").pack(anchor="w")

        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="n", pady=18)

        def nav_btn(text, active=False, command=None):
            if active:
                return ctk.CTkButton(
                    nav, text=text,
                    height=34, corner_radius=999,
                    fg_color="#E6F0FF", hover_color="#D6E7FF",
                    text_color=PRIMARY,
                    font=(FONT, 13, "bold"),
                    command=command
                )
            return ctk.CTkButton(
                nav, text=text,
                height=34, corner_radius=999,
                fg_color="transparent", hover_color="#F1F5F9",
                text_color="#334155",
                font=(FONT, 13),
                command=command
            )

        def go_dashboard():
            for w in self.master.winfo_children():
                w.destroy()
            DashboardFrame(self.master, on_logout=self.on_logout)

        def go_patients():
            # ถ้า import ด้านบนชนกัน ให้ย้าย import มาไว้ตรงนี้แทน
            # from patients_list import patientsListFrame
            for w in self.master.winfo_children():
                w.destroy()
            patientsListFrame(self.master)

        def go_report():
            tk.messagebox.showinfo("รายงาน", "ยังไม่ทำหน้า Report")

        nav_btn("Dashboard", active=True, command=go_dashboard).pack(side="left", padx=8)
        nav_btn("รายชื่อผู้ป่วย", active=False, command=go_patients).pack(side="left", padx=8)
        nav_btn("รายงาน", active=False, command=go_report).pack(side="left", padx=8)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=0, sticky="e", padx=18, pady=12)

        self.time_lbl = ctk.CTkLabel(right, text="", font=(FONT, 12, "bold"), text_color="#334155")
        self.time_lbl.pack(side="left", padx=10)

        ctk.CTkLabel(right, text="🧑‍⚕️ แพทย์", font=(FONT, 13, "bold"), text_color="#0f172a").pack(side="left", padx=10)

        if self.on_logout:
            ctk.CTkButton(
                right,
                text="ออกจากระบบ",
                fg_color="#ef4444",
                hover_color="#dc2626",
                font=(FONT, 13, "bold"),
                corner_radius=14,
                height=36,
                command=self.on_logout,
            ).pack(side="left", padx=10)

    def _start_clock(self):
        def tick():
            now = datetime.now()
            self.time_lbl.configure(text=now.strftime("%d %b %Y  %H:%M:%S"))
            self.after(1000, tick)
        tick()

    # ---------- Scroll ----------
    def _build_scroll_area(self):
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        vbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        vbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=vbar.set)

        self.body = ctk.CTkFrame(self.canvas, fg_color=BG)
        self.body_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.body_id, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # ---------- Main content ----------
    def _build_content(self):
        wrap = ctk.CTkFrame(self.body, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=24)

        ctk.CTkLabel(wrap, text="Dashboard แพทย์", font=(FONT, 30, "bold"), text_color=PRIMARY).pack(anchor="w")
        ctk.CTkLabel(wrap, text="ภาพรวมผู้ป่วยและข้อมูลสำคัญล่าสุด", font=(FONT, 15), text_color="#64748B").pack(anchor="w", pady=(6, 18))

        # ---- 4 Stat cards ----
        stats_row = ctk.CTkFrame(wrap, fg_color="transparent")
        stats_row.pack(fill="x")
        stats_row.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")

        self._stat_total(stats_row, 0, "ผู้ป่วยทั้งหมด", self.stats["all"], border="#60A5FA")
        self._stat_today(stats_row, 1, "ผู้ป่วยที่ประเมินวันนี้", self.stats["today"], border="#6366F1")
        self._stat_month(stats_row, 2, "ผู้ป่วยเดือนนี้", self.stats["month"], border="#06B6D4")
        self._stat_year(stats_row, 3, "ผู้ป่วยรายปี (ปีนี้)", self.stats["year"], border="#10B981")

        # ✅ Quick Actions (ย้ายมาไว้ “ก่อนกราฟ” ตามที่สั่ง)
        self._build_quick_actions(wrap)

        # ---- Charts row ----
        charts2 = ctk.CTkFrame(wrap, fg_color="transparent")
        charts2.pack(fill="x", pady=(8, 0))
        charts2.grid_columnconfigure((0, 1), weight=1, uniform="c2")

        left = card(charts2, radius=22)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=10)
        self._chart_header(left, "📊", "การกระจายตามระดับความเสี่ยง", "สัดส่วนผู้ป่วยแต่ละกลุ่ม")
        self._plot_risk_pie(left, *self.risk)

        right = card(charts2, radius=22)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=10)
        self._chart_header(right, "👥", "การกระจายตามช่วงอายุ", "จำนวนผู้ป่วยในแต่ละช่วงอายุ (ชาย / หญิง)")
        self._plot_age_bar(right, *self.age)

        trend_card = card(wrap, radius=22)
        trend_card.pack(fill="x", pady=(10, 0))
        self._chart_header(trend_card, "📈", "แนวโน้มรายเดือน", "จำนวนผู้ป่วยและการประเมินในแต่ละเดือน")
        self._plot_month_trend(trend_card, *self.trend)

        ctk.CTkLabel(
            wrap,
            text="© 2024-2025 | ระบบประเมินสุขภาพผู้สูงอายุ โรงพยาบาลพะเยา",
            font=(FONT, 11),
            text_color="#94a3b8",
        ).pack(pady=(16, 10))

    # ---------- Stat cards ----------
    def _stat_shell(self, parent, col, border):
        box = card(parent, radius=22)
        box.grid(row=0, column=col, sticky="nsew", padx=10, pady=10)
        box.configure(border_width=2, border_color=border)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        return inner

    def _stat_total(self, parent, col, title, value, border):
        inner = self._stat_shell(parent, col, border)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        pill(top, "ทั้งหมด", fg="#E6F0FF", tc=border).pack(side="right")

        ctk.CTkLabel(inner, text=str(value), font=(FONT, 44, "bold"), text_color="#0f172a").pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(inner, text=title, font=(FONT, 14), text_color="#64748B").pack(anchor="w")

    def _stat_today(self, parent, col, title, value, border):
        inner = self._stat_shell(parent, col, border)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        pill(top, "วันนี้", fg="#EEF2FF", tc=border).pack(side="right")

        ctk.CTkLabel(inner, text=str(value), font=(FONT, 44, "bold"), text_color="#0f172a").pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(inner, text=title, font=(FONT, 14), text_color="#64748B").pack(anchor="w")

        _, self.today_entry = make_entry_with_icon(
            inner,
            placeholder="dd/mm/yyyy",
            icon="📅",
            command=lambda: self.open_day_picker(self.today_entry, border),
        )

        q = ctk.CTkFrame(inner, fg_color="transparent")
        q.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(
            q, text="วันนี้", width=90, height=34, corner_radius=10,
            fg_color=border, hover_color=border,
            font=(FONT, 12, "bold"),
            command=lambda: self.apply_quick_filter("today"),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            q, text="สัปดาห์นี้", width=110, height=34, corner_radius=10,
            fg_color="#0ea5e9", hover_color="#0284c7",
            font=(FONT, 12, "bold"),
            command=lambda: self.apply_quick_filter("week"),
        ).pack(side="left")

        ctk.CTkButton(
            inner, text="ค้นหา", height=40, corner_radius=12,
            fg_color=border, hover_color=border,
            font=(FONT, 13, "bold"),
            command=self._search_today,
        ).pack(fill="x")

    def _stat_month(self, parent, col, title, value, border):
        inner = self._stat_shell(parent, col, border)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        pill(top, "เดือนนี้", fg="#E0F2FE", tc=border).pack(side="right")

        ctk.CTkLabel(inner, text=str(value), font=(FONT, 44, "bold"), text_color="#0f172a").pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(inner, text=title, font=(FONT, 14), text_color="#64748B").pack(anchor="w")

        _, self.month_entry = make_entry_with_icon(
            inner,
            placeholder="mm/yyyy (เช่น 12/2025)",
            icon="📅",
            command=lambda: self.open_month_picker(self.month_entry),
        )

        ctk.CTkButton(
            inner, text="เดือนนี้อัตโนมัติ", height=34, corner_radius=10,
            fg_color=border, hover_color=border,
            font=(FONT, 12, "bold"),
            command=lambda: self.apply_quick_filter("month"),
        ).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            inner, text="ค้นหา", height=40, corner_radius=12,
            fg_color=border, hover_color=border,
            font=(FONT, 13, "bold"),
            command=self._search_month,
        ).pack(fill="x")

    def _stat_year(self, parent, col, title, value, border):
        inner = self._stat_shell(parent, col, border)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        pill(top, "รายปี", fg="#DCFCE7", tc=border).pack(side="right")

        ctk.CTkLabel(inner, text=str(value), font=(FONT, 44, "bold"), text_color="#0f172a").pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(inner, text=title, font=(FONT, 14), text_color="#64748B").pack(anchor="w")

        _, self.year_entry = make_entry_with_icon(
            inner,
            placeholder="เช่น 2025",
            icon="📅",
            command=lambda: self.open_year_picker(self.year_entry),
        )

        ctk.CTkButton(
            inner, text="ค้นหา", height=40, corner_radius=12,
            fg_color=border, hover_color=border,
            font=(FONT, 13, "bold"),
            command=self._search_year,
        ).pack(fill="x")

    # ---------- Quick filters / pickers ----------
    def apply_quick_filter(self, mode: str):
        today = date.today()

        if mode == "today":
            start = end = today
            self.today_entry.delete(0, "end")
            self.today_entry.insert(0, today.strftime("%d/%m/%Y"))

        elif mode == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            self.today_entry.delete(0, "end")
            self.today_entry.insert(0, f"{start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}")

        elif mode == "month":
            start = date(today.year, today.month, 1)
            last = calendar.monthrange(today.year, today.month)[1]
            end = date(today.year, today.month, last)
            self.month_entry.delete(0, "end")
            self.month_entry.insert(0, f"{today.month:02d}/{today.year}")

        else:
            return

        self.filter_range = (start, end)
        print("Filter range:", self.filter_range)

    def open_day_picker(self, target_entry, border_color=PRIMARY):
        popup = tk.Toplevel(self)
        popup.title("เลือกวันที่")
        popup.configure(bg="white")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        _center_popup(popup, self, 360, 380)

        cal = Calendar(
            popup,
            selectmode="day",
            date_pattern="dd/mm/yyyy",
            background=PRIMARY,
            foreground="white",
            headersbackground=PRIMARY,
            headersforeground="white",
            selectbackground=PRIMARY_HOVER,
            selectforeground="white",
            normalbackground="white",
            normalforeground="#0f172a",
            weekendbackground="white",
            weekendforeground="#0f172a",
            othermonthbackground="#F3F4F6",
            othermonthforeground="#94a3b8",
            bordercolor="#e5e7eb",
        )
        cal.pack(padx=14, pady=14, fill="both", expand=True)

        def use_date():
            d = cal.get_date()
            target_entry.delete(0, "end")
            target_entry.insert(0, d)
            dt = datetime.strptime(d, "%d/%m/%Y").date()
            self.filter_range = (dt, dt)
            popup.destroy()

        ctk.CTkButton(
            popup,
            text="เลือกวันที่",
            fg_color=border_color,
            hover_color=border_color,
            font=(FONT, 14, "bold"),
            command=use_date,
            height=42,
            corner_radius=12,
        ).pack(padx=14, pady=(0, 14), fill="x")

    def open_month_picker(self, target_entry):
        popup = ctk.CTkToplevel(self)
        popup.title("เลือกเดือน/ปี")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        _center_popup(popup, self, 360, 230)

        now = datetime.now()
        months = _thai_month_names()

        wrap = ctk.CTkFrame(popup, fg_color="white", corner_radius=16)
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(wrap, text="เลือกเดือน", font=(FONT, 14, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        m_var = tk.StringVar(value=months[now.month - 1])
        m_menu = ctk.CTkOptionMenu(wrap, values=months, variable=m_var, fg_color=PRIMARY, button_color=PRIMARY_HOVER)
        m_menu.pack(fill="x", padx=12)

        ctk.CTkLabel(wrap, text="เลือกปี (ค.ศ.)", font=(FONT, 14, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        y_var = tk.IntVar(value=now.year)
        y_entry = ctk.CTkEntry(wrap, textvariable=y_var, font=(FONT, 13))
        y_entry.pack(fill="x", padx=12)

        def use_month():
            m = months.index(m_var.get()) + 1
            y = int(y_var.get())

            target_entry.delete(0, "end")
            target_entry.insert(0, f"{m:02d}/{y}")

            start = date(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            end = date(y, m, last_day)
            self.filter_range = (start, end)
            popup.destroy()

        ctk.CTkButton(
            wrap,
            text="เลือก",
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            font=(FONT, 14, "bold"),
            command=use_month,
            height=40,
            corner_radius=12,
        ).pack(fill="x", padx=12, pady=12)

    def open_year_picker(self, target_entry):
        popup = ctk.CTkToplevel(self)
        popup.title("เลือกปี")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        _center_popup(popup, self, 320, 190)

        now = datetime.now()

        wrap = ctk.CTkFrame(popup, fg_color="white", corner_radius=16)
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(wrap, text="เลือกปี (ค.ศ.)", font=(FONT, 14, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        y_var = tk.IntVar(value=now.year)
        y_entry = ctk.CTkEntry(wrap, textvariable=y_var, font=(FONT, 13))
        y_entry.pack(fill="x", padx=12)

        def use_year():
            y = int(y_var.get())
            target_entry.delete(0, "end")
            target_entry.insert(0, str(y))
            self.filter_range = (date(y, 1, 1), date(y, 12, 31))
            popup.destroy()

        ctk.CTkButton(
            wrap,
            text="เลือก",
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            font=(FONT, 14, "bold"),
            command=use_year,
            height=40,
            corner_radius=12,
        ).pack(fill="x", padx=12, pady=12)

    # ---------- Demo searches ----------
    def _search_today(self):
        print("ค้นหาวัน:", self.today_entry.get(), "| range:", self.filter_range)

    def _search_month(self):
        print("ค้นหาเดือน:", self.month_entry.get(), "| range:", self.filter_range)

    def _search_year(self):
        print("ค้นหาปี:", self.year_entry.get(), "| range:", self.filter_range)

    # ---------- Charts ----------
    def _chart_header(self, parent, icon, title, subtitle):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 6))

        badge = ctk.CTkFrame(header, width=44, height=44, corner_radius=14, fg_color="#E0F2FE")
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text=icon, font=(FONT, 18)).pack(expand=True)

        texts = ctk.CTkFrame(header, fg_color="transparent")
        texts.pack(side="left", padx=12)
        ctk.CTkLabel(texts, text=title, font=(FONT, 16, "bold"), text_color="#0f172a").pack(anchor="w")
        ctk.CTkLabel(texts, text=subtitle, font=(FONT, 12), text_color="#64748B").pack(anchor="w")

    def _embed_plot(self, parent, fig):
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        canvas = FigureCanvasTkAgg(fig, master=holder)
        canvas.draw()
        w = canvas.get_tk_widget()
        w.configure(highlightthickness=0, bd=0)
        w.pack(fill="both", expand=True)

    def _plot_risk_pie(self, parent, labels, values):
        fig = Figure(figsize=(5, 3.2), dpi=100)
        ax = fig.add_subplot(111)
        if sum(values) == 0:
            values = [1, 1, 1]
        ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
        ax.axis("equal")
        fig.tight_layout()
        self._embed_plot(parent, fig)

    def _plot_age_bar(self, parent, bins, male, female):
        fig = Figure(figsize=(5, 3.2), dpi=100)
        ax = fig.add_subplot(111)
        x = list(range(len(bins)))
        w = 0.35
        ax.bar([i - w / 2 for i in x], male, width=w, label="ชาย")
        ax.bar([i + w / 2 for i in x], female, width=w, label="หญิง")
        ax.set_xticks(x)
        ax.set_xticklabels(bins)
        ax.set_ylim(0, max([1] + male + female) + 1)
        ax.legend()
        fig.tight_layout()
        self._embed_plot(parent, fig)

    def _plot_month_trend(self, parent, months, assessed, patients):
        fig = Figure(figsize=(10, 3.4), dpi=100)
        ax = fig.add_subplot(111)
        x = list(range(len(months)))
        ax.plot(x, assessed, marker="o", label="การประเมิน")
        ax.plot(x, patients, marker="o", label="ผู้ป่วย")
        ax.fill_between(x, assessed, alpha=0.15)
        ax.fill_between(x, patients, alpha=0.15)
        ax.set_xticks(x)
        ax.set_xticklabels(months)
        ax.legend()
        fig.tight_layout()
        self._embed_plot(parent, fig)

    # ---------- Quick actions (เหมือนรูป) ----------
    def _build_quick_actions(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(18, 10))

        ctk.CTkLabel(head, text="🗓️", font=(FONT, 22)).pack(side="left")
        ctk.CTkLabel(head, text="การดำเนินการด่วน", font=(FONT, 20, "bold"), text_color=PRIMARY).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(head, text="●", font=(FONT, 16, "bold"), text_color="#ef4444").pack(side="left", padx=8)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        for i in range(4):
            row.grid_columnconfigure(i, weight=1, uniform="qa")

        self._quick_card(row, 0, title="ผู้ป่วยนัดหมาย", emoji="📅", bg="#EEF2FF", border="#C7D2FE", tc="#6D28D9", command=self.on_appointments)
        self._quick_card(row, 1, title="ผู้ป่วยส่งต่อ", emoji="👥", bg="#E0F2FE", border="#BAE6FD", tc="#2563eb", command=self.on_referrals)
        self._quick_card(row, 2, title="ผู้ป่วยเร่งด่วน", emoji="🚨", bg="#FEE2E2", border="#FCA5A5", tc="#DC2626", command=self.on_urgent)
        self._quick_card(row, 3, title="ออกรายงาน", emoji="📄", bg="#DCFCE7", border="#86EFAC", tc="#15803D", command=self.on_reports)

    def _quick_card(self, parent, col, title, emoji, bg, border, tc, command=None):
        box = ctk.CTkFrame(parent, fg_color=bg, corner_radius=22, border_width=2, border_color=border)
        box.grid(row=0, column=col, sticky="nsew", padx=10, pady=10)

        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(inner, text=emoji, font=(FONT, 44)).pack(pady=(10, 6))
        ctk.CTkLabel(inner, text=title, font=(FONT, 22, "bold"), text_color=tc).pack()

        if command:
            box.bind("<Button-1>", lambda e: command())
            inner.bind("<Button-1>", lambda e: command())

    def on_appointments(self):
        print("ไปหน้า: ผู้ป่วยนัดหมาย")

    def on_referrals(self):
        print("ไปหน้า: ผู้ป่วยส่งต่อ")

    def on_urgent(self):
        print("ไปหน้า: ผู้ป่วยเร่งด่วน")

    def on_reports(self):
        print("ไปหน้า: ออกรายงาน")


# =========================
# Optional: run standalone
# =========================
def open_dashboard(on_logout=None):
    root = ctk.CTk()
    root.title("Dashboard แพทย์ | ระบบประเมินสุขภาพผู้สูงอายุ")
    root.geometry("1200x820")
    root.minsize(1100, 760)
    DashboardFrame(root, on_logout=on_logout)
    root.mainloop()
