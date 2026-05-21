"""
HTML email body builder for key scan and rotation reports.
Modern, premium look — refined palette, system-stack typography, soft shadows,
pill badges, and a violet/indigo gradient header.
"""

from __future__ import annotations

import html as _html

from src.rotator import (
    AUTO_ROTATE_THRESHOLD_DAYS,
    EXPIRING_SOON_THRESHOLD_DAYS,
    OK_THRESHOLD_DAYS,
    RotationRecord,
)


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
# Type system:
#   Body / UI : Plus Jakarta Sans  — humanist sans, premium feel (Linear / Vercel / Stripe-tier)
#   Display   : same family, weight 700/800 + tight tracking for headings
#   Mono      : JetBrains Mono     — used for emails, project IDs, code chips
# Clients that strip @import (Outlook desktop, Gmail web partially) fall back
# cleanly to the platform UI font (SF Pro / Segoe UI Variable / Roboto).
FONT_STACK = (
    "'Plus Jakarta Sans','Inter',-apple-system,BlinkMacSystemFont,"
    "'SF Pro Text','Segoe UI Variable','Segoe UI',Roboto,"
    "'Helvetica Neue',Arial,sans-serif"
)
DISPLAY_STACK = FONT_STACK  # same family; display variant is purely weight + tracking
MONO_STACK = (
    "'JetBrains Mono','SF Mono','SFMono-Regular',ui-monospace,Menlo,"
    "Consolas,'Liberation Mono',monospace"
)

# Neutrals (slate scale)
INK_900 = "#0B1220"
INK_800 = "#1E293B"
INK_700 = "#334155"
INK_500 = "#64748B"
INK_400 = "#94A3B8"
LINE    = "#E2E8F0"
LINE_2  = "#EEF2F7"
SURFACE = "#FFFFFF"
CANVAS  = "#F4F6FB"
SOFT    = "#F8FAFC"

# Brand
BRAND_DEEP = "#3730A3"   # indigo-800
BRAND      = "#4F46E5"   # indigo-600
BRAND_SOFT = "#EEF2FF"   # indigo-50
BRAND_LINE = "#C7D2FE"   # indigo-200
ACCENT     = "#7C3AED"   # violet-600
ACCENT_HI  = "#A78BFA"   # violet-400

# Status palette (foreground / background / border)
STATUS_TOKENS = {
    "Rotated":        ("#047857", "#ECFDF5", "#A7F3D0"),
    "OK":             ("#047857", "#ECFDF5", "#A7F3D0"),
    "Expiring Soon":  ("#B45309", "#FFFBEB", "#FCD34D"),
    "Critical":       ("#C2410C", "#FFF7ED", "#FDBA74"),
    "Very Critical":  ("#FFFFFF", "#BE123C", "#9F1239"),
    "Error":          ("#B91C1C", "#FEF2F2", "#FCA5A5"),
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _auto_notice_text() -> str:
    return (
        "This is an automatically generated email. For questions or concerns, "
        "please contact the DevOps team."
    )


def _wrap_html_email(*, subject: str, body_html: str) -> str:
    subj = _html.escape(subject or "", quote=False)
    notice = _html.escape(_auto_notice_text(), quote=False)
    return f"""<!doctype html>
<html lang="en" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="color-scheme" content="light" />
    <meta name="supported-color-schemes" content="light" />
    <title>{subj}</title>
    <!--[if gte mso 9]>
    <xml>
      <o:OfficeDocumentSettings>
        <o:AllowPNG/>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
    <![endif]-->
    <!--[if mso]>
    <style type="text/css">
      * {{ font-family: 'Segoe UI', Arial, sans-serif !important; }}
      table, td {{ border-collapse: collapse !important; mso-table-lspace: 0pt !important; mso-table-rspace: 0pt !important; }}
      a {{ text-decoration: none; }}
      .mso-hide {{ display: none !important; mso-hide: all !important; }}
    </style>
    <![endif]-->
    <!-- Web fonts (ignored by Outlook/Gmail-stripping clients; falls back to system) -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
    <style type="text/css">
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
      body, table, td, div, p, span, a {{
        -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;
        -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
        text-rendering:optimizeLegibility;
        font-feature-settings:'cv11','ss01','ss03','kern';
      }}
      table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; border-collapse:collapse; }}
      img {{ -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; }}
      p {{ margin:0; }}
    </style>
  </head>
  <body style="margin:0;padding:0;background-color:{CANVAS};
    mso-line-height-rule:exactly;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="border-collapse:collapse;background-color:{CANVAS};
      mso-table-lspace:0pt;mso-table-rspace:0pt;">
      <tr>
        <td align="center" style="padding:36px 16px;">
          <table role="presentation" width="680" cellspacing="0" cellpadding="0" border="0"
            style="border-collapse:collapse;max-width:680px;width:100%;
            mso-table-lspace:0pt;mso-table-rspace:0pt;">
            <tr>
              <td style="padding:0;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                  style="border-collapse:collapse;background-color:{SURFACE};
                  border:1px solid {LINE};border-radius:20px;overflow:hidden;
                  mso-table-lspace:0pt;mso-table-rspace:0pt;
                  box-shadow:0 24px 48px -16px rgba(15,23,42,0.18),
                             0 4px 12px -4px rgba(15,23,42,0.08);">
                  <!-- Header -->
                  <tr>
                    <td style="padding:0;background-color:{BRAND_DEEP};
                      background-image:linear-gradient(135deg,{BRAND_DEEP} 0%,{BRAND} 45%,{ACCENT} 100%);
                      mso-padding-alt:32px 30px 30px 30px;">
                      <div style="padding:32px 30px 30px 30px;font-family:{DISPLAY_STACK};
                        mso-line-height-rule:exactly;">
                        <div style="display:inline-block;padding:6px 12px;border-radius:999px;
                          background-color:#5B53E9;
                          color:#FFFFFF;font-size:10.5px;font-weight:700;mso-text-raise:1px;
                          letter-spacing:0.16em;text-transform:uppercase;line-height:1.2;">
                          Devops Team &middot; Movate
                        </div>
                        <div style="margin-top:16px;font-size:28px;font-weight:800;line-height:1.15;
                          color:#FFFFFF;letter-spacing:-0.03em;">
                          GCP Service Account Key Report
                        </div>
                        <div style="margin-top:10px;font-size:14px;color:#E0E7FF;line-height:1.55;
                          font-weight:500;letter-spacing:-0.005em;">
                          Automated key expiry scan and rotation summary
                        </div>
                      </div>
                    </td>
                  </tr>
                  <!-- Title -->
                  <tr>
                    <td style="padding:26px 30px 6px 30px;background-color:{SURFACE};">
                      <div style="font-family:{DISPLAY_STACK};font-size:18px;font-weight:700;
                        line-height:1.35;color:{INK_900};letter-spacing:-0.022em;">
                        {subj}
                      </div>
                      <div style="margin-top:12px;height:3px;width:56px;border-radius:2px;
                        background-color:{BRAND};
                        background-image:linear-gradient(90deg,{BRAND} 0%,{ACCENT_HI} 100%);
                        font-size:1px;line-height:3px;">&nbsp;</div>
                    </td>
                  </tr>
                  <!-- Body -->
                  <tr>
                    <td style="padding:12px 30px 30px 30px;background-color:{SURFACE};">
                      <div style="font-family:{FONT_STACK};font-size:14.5px;line-height:1.7;
                        color:{INK_700};font-weight:500;letter-spacing:-0.003em;">
                        {body_html}
                      </div>
                    </td>
                  </tr>
                  <!-- Footer notice -->
                  <tr>
                    <td style="padding:20px 30px;background-color:{SOFT};
                      border-top:1px solid {LINE_2};">
                      <div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;
                        color:{INK_500};font-weight:500;">
                        <span style="display:inline-block;padding:3px 10px;border-radius:999px;
                          background-color:{BRAND_SOFT};color:{BRAND};font-weight:700;
                          font-size:10px;letter-spacing:0.1em;text-transform:uppercase;
                          margin-right:8px;">Auto</span>
                        <strong style="color:{INK_700};font-weight:700;">Notice</strong>
                        <span style="color:{INK_400};"> &middot; </span>
                        {notice}
                      </div>
                    </td>
                  </tr>
                </table>
                <div style="margin-top:20px;font-family:{FONT_STACK};font-size:11.5px;
                  color:{INK_400};text-align:center;line-height:1.5;font-weight:500;
                  letter-spacing:0.01em;">
                  This message was sent automatically &middot; Please do not reply
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


# ---------------------------------------------------------------------------
# Metric summary card
# ---------------------------------------------------------------------------

def _metrics_html(records: list[RotationRecord], rotation_enabled: bool) -> str:
    total = len(records)
    ok = sum(1 for r in records if r.status == "OK")
    expiring_soon = sum(1 for r in records if r.status == "Expiring Soon")
    critical = sum(1 for r in records if r.status == "Critical")
    very_critical = sum(1 for r in records if r.status == "Very Critical")
    rotated = sum(1 for r in records if r.status == "Rotated")
    errors = sum(1 for r in records if r.status == "Error")

    label = (
        f"font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.11em;"
        f"color:{INK_500};font-family:{FONT_STACK};margin-bottom:10px;"
    )
    val_base = (
        f"font-size:28px;font-weight:800;color:{INK_900};"
        f"font-family:{DISPLAY_STACK};letter-spacing:-0.04em;line-height:1;"
        f"font-variant-numeric:tabular-nums lining-nums;"
    )

    def val_color(hex_color: str) -> str:
        return val_base.replace(INK_900, hex_color)

    val_warn  = val_color("#B45309")
    val_crit  = val_color("#C2410C")
    val_vcrit = val_color("#BE123C")
    val_err   = val_color("#B91C1C")
    val_ok    = val_color("#047857")

    if rotation_enabled:
        cells = [
            ("Rotated",       str(rotated),       val_ok    if rotated       else val_base),
            ("Very Critical", str(very_critical), val_vcrit if very_critical else val_base),
            ("Critical",      str(critical),      val_crit  if critical      else val_base),
            ("Errors",        str(errors),        val_err   if errors        else val_base),
        ]
    else:
        cells = [
            ("Very Critical", str(very_critical), val_vcrit if very_critical else val_base),
            ("Critical",      str(critical),      val_crit  if critical      else val_base),
            ("Expiring Soon", str(expiring_soon), val_warn  if expiring_soon else val_base),
            ("Safe / OK",     f"{ok}/{total}",    val_ok),
        ]

    tds = ""
    for i, (lbl, v, v_style) in enumerate(cells):
        border = "" if i == len(cells) - 1 else f"border-right:1px solid {LINE};"
        tds += (
            f'<td style="padding:18px 18px;{border}vertical-align:top;width:25%;">'
            f'<div style="{label}">{_html.escape(lbl)}</div>'
            f'<div style="{v_style}">{v}</div>'
            f'</td>'
        )

    return f"""
<div style="margin:0 0 22px 0;padding:6px;border-radius:16px;
  background-color:{SURFACE};
  background-image:linear-gradient(180deg,{SURFACE} 0%,{SOFT} 100%);
  border:1px solid {LINE};box-shadow:0 1px 2px rgba(15,23,42,0.04);">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
    style="border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;">
    <tr>{tds}</tr>
  </table>
</div>
""".strip()


# ---------------------------------------------------------------------------
# Key details table
# ---------------------------------------------------------------------------

def _key_table_html(records: list[RotationRecord], rotation_enabled: bool) -> str:
    """Build an HTML table of up to 5 key records appropriate for the current mode."""
    th = (
        f"padding:13px 14px;font-size:10.5px;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.11em;color:{INK_500};font-family:{FONT_STACK};"
        f"background-color:{SOFT};border-bottom:1px solid {LINE};text-align:left;"
    )

    _priority = {
        "Error": 0,
        "Very Critical": 1,
        "Critical": 2,
        "Rotated": 3,
        "Expiring Soon": 4,
        "OK": 5,
    }

    notable = ("Rotated", "Error", "Very Critical", "Critical", "Expiring Soon")
    if rotation_enabled:
        display_records = [r for r in records if r.status in notable]
        headers = ["Service Account", "Project", "Expiry Date", "Days Left", "Status"]
    else:
        display_records = [r for r in records if r.status in ("Very Critical", "Critical", "Expiring Soon", "Error")] or list(records)
        headers = ["Service Account", "Project", "Expiry Date", "Days Remaining", "Status"]

    display_records = sorted(display_records, key=lambda r: _priority.get(r.status, 99))[:5]

    if not display_records:
        msg = "No keys require attention." if rotation_enabled else "No keys found."
        return (
            f'<div style="padding:20px;border:1px dashed {LINE};border-radius:14px;'
            f'background-color:{SOFT};text-align:center;">'
            f'<p style="margin:0;color:{INK_500};font-size:14px;font-family:{FONT_STACK};">'
            f'{msg}</p></div>'
        )

    header_row = "".join(f'<th style="{th}">{h}</th>' for h in headers)

    td_base = (
        f"padding:14px 14px;font-size:13px;font-family:{FONT_STACK};"
        f"border-bottom:1px solid {LINE_2};vertical-align:middle;color:{INK_800};"
        f"font-weight:500;"
    )

    body_rows = []
    for i, rec in enumerate(display_records):
        bg = SOFT if i % 2 == 0 else SURFACE
        expiry_str = rec.expiry_date.strftime("%Y-%m-%d") if rec.expiry_date else "N/A"
        days_str = "Default" if rec.days_remaining is not None and rec.days_remaining > 36500 else (str(rec.days_remaining) if rec.days_remaining is not None else "N/A")
        fg, sbg, sbr = STATUS_TOKENS.get(rec.status, (INK_700, "#F3F4F6", LINE))

        status_badge = (
            f'<span style="display:inline-block;padding:4px 11px;border-radius:999px;'
            f'background-color:{sbg};color:{fg};font-weight:700;font-size:11px;'
            f'border:1px solid {sbr};letter-spacing:0.025em;font-family:{FONT_STACK};'
            f'white-space:nowrap;">{_html.escape(rec.status)}</span>'
        )

        sa_cell = (
            f'<span style="font-family:{MONO_STACK};font-size:12.5px;color:{INK_900};'
            f'font-weight:500;letter-spacing:-0.005em;">'
            f'{_html.escape(rec.sa_email)}</span>'
        )

        project_cell = (
            f'<span style="color:{INK_900};font-weight:700;letter-spacing:-0.01em;">'
            f'{_html.escape(rec.project_name or rec.project_id)}</span>'
        )
        if rec.project_name and rec.project_name != rec.project_id:
            project_cell += (
                f'<br><span style="font-size:11.5px;color:{INK_500};font-family:{MONO_STACK};'
                f'font-weight:500;">'
                f'{_html.escape(rec.project_id)}</span>'
            )

        days_cell = (
            f'<span style="font-variant-numeric:tabular-nums lining-nums;'
            f'font-weight:700;color:{INK_900};font-family:{DISPLAY_STACK};">'
            f'{_html.escape(days_str)}</span>'
        )
        date_cell = (
            f'<span style="font-variant-numeric:tabular-nums lining-nums;color:{INK_700};">'
            f'{_html.escape(expiry_str)}</span>'
        )

        cells = [sa_cell, project_cell, date_cell, days_cell, status_badge]
        tds = "".join(
            f'<td style="{td_base}background-color:{bg};">{c}</td>' for c in cells
        )
        body_rows.append(f'<tr>{tds}</tr>')

    if rotation_enabled:
        total = len([r for r in records if r.status in notable])
    else:
        total = len([r for r in records if r.status in ("Very Critical", "Critical", "Expiring Soon", "Error")]) or len(records)
    overflow_note = (
        f'<tr><td colspan="{len(headers)}" style="padding:12px 14px;font-size:12px;'
        f'color:{INK_500};font-family:{FONT_STACK};background-color:{SOFT};'
        f'border-top:1px solid {LINE_2};">'
        f'Showing <strong style="color:{INK_700};">5</strong> of '
        f'<strong style="color:{INK_700};">{total}</strong> &middot; see attachment for full list.'
        f'</td></tr>'
        if total > 5 else ""
    )

    return f"""
<div style="margin:22px 0 0 0;border-radius:16px;overflow:hidden;border:1px solid {LINE};
  box-shadow:0 8px 24px -12px rgba(15,23,42,0.12),0 2px 6px -2px rgba(15,23,42,0.06);
  background-color:{SURFACE};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
    style="border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;">
    <thead>
      <tr>
        <th colspan="{len(headers)}" align="left"
          style="padding:18px 20px;background-color:{BRAND_DEEP};
          background-image:linear-gradient(135deg,{BRAND_DEEP} 0%,{BRAND} 60%,{ACCENT} 100%);
          mso-padding-alt:18px 20px;">
          <span style="font-family:{DISPLAY_STACK};font-size:16px;font-weight:700;
            color:#FFFFFF;letter-spacing:-0.025em;">
            {"Key Rotation Results" if rotation_enabled else "Key Expiry Scan Results"}
          </span>
          <span style="display:block;margin-top:6px;font-size:12.5px;font-weight:500;
            color:#E0E7FF;font-family:{FONT_STACK};letter-spacing:-0.003em;">
            {"Showing rotated and errored keys" if rotation_enabled else "All USER_MANAGED keys across configured projects"}
          </span>
        </th>
      </tr>
      <tr>{header_row}</tr>
    </thead>
    <tbody>
      {"".join(body_rows)}
      {overflow_note}
    </tbody>
  </table>
</div>
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_email_body(
    records: list[RotationRecord],
    subject: str,
    attachment_name: str,
    rotation_enabled: bool,
) -> str:
    """Build and return the full HTML email string."""
    mode_label = "Rotation Report" if rotation_enabled else "Scan Report"
    if rotation_enabled:
        mode_fg, mode_bg, mode_br = "#047857", "#ECFDF5", "#A7F3D0"
    else:
        mode_fg, mode_bg, mode_br = BRAND, BRAND_SOFT, BRAND_LINE

    if rotation_enabled:
        intro = (
            "New key files have been generated and stored. "
            "Please verify the new credentials before retiring the old keys. "
            "Old keys have <strong>not</strong> been deleted automatically."
        )
    else:
        intro = (
            "The attached Excel workbook contains the full results for all projects. "
            f"Keys marked <strong>Very Critical</strong> have &le; {AUTO_ROTATE_THRESHOLD_DAYS} days remaining, "
            f"<strong>Critical</strong> are {AUTO_ROTATE_THRESHOLD_DAYS + 1}&ndash;{EXPIRING_SOON_THRESHOLD_DAYS} days, "
            f"<strong>Expiring Soon</strong> are {EXPIRING_SOON_THRESHOLD_DAYS + 1}&ndash;{OK_THRESHOLD_DAYS} days."
        )

    auto_rotate_notice = (
        f'<div style="margin:0 0 20px 0;padding:14px 18px;border-radius:12px;'
        f'background-color:#FFFBEB;'
        f'background-image:linear-gradient(180deg,#FFFBEB 0%,#FEF3C7 100%);'
        f'border:1px solid #FDE68A;border-left:4px solid #D97706;'
        f'box-shadow:0 1px 2px rgba(217,119,6,0.08);">'
        f'<div style="font-family:{FONT_STACK};font-size:10.5px;font-weight:700;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:#92400E;margin-bottom:4px;">'
        f'Auto-rotate policy</div>'
        f'<span style="font-family:{FONT_STACK};font-size:13.5px;color:#7C2D12;'
        f'line-height:1.6;">'
        f'Keys within <strong>{AUTO_ROTATE_THRESHOLD_DAYS} days</strong> of expiry will '
        f'auto rotate on the next scheduled run (weekly, when '
        f'<code style="font-family:{MONO_STACK};font-size:12px;background-color:#FEF3C7;'
        f'padding:1px 6px;border-radius:5px;border:1px solid #FDE68A;color:#92400E;">'
        f'ENABLE_ROTATION</code> is on).'
        f'</span></div>'
    )

    content_html = f"""
<p style="margin:0 0 18px 0;font-family:{DISPLAY_STACK};font-size:17px;
  font-weight:700;color:{INK_900};letter-spacing:-0.02em;">Hi Team,</p>

<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
  style="border-collapse:separate;margin:0 0 20px 0;border-radius:14px;
  background-color:{BRAND_SOFT};
  background-image:linear-gradient(180deg,{BRAND_SOFT} 0%,#F5F3FF 100%);
  border:1px solid {BRAND_LINE};mso-table-lspace:0pt;mso-table-rspace:0pt;">
  <tr>
    <td style="width:6px;background-color:{BRAND};border-top-left-radius:14px;
      border-bottom-left-radius:14px;font-size:1px;line-height:1px;">&nbsp;</td>
    <td style="padding:14px 18px;">
      <div style="margin-bottom:6px;">
        <span style="display:inline-block;padding:3px 10px;border-radius:999px;
          background-color:{mode_bg};color:{mode_fg};font-weight:700;font-size:11px;
          font-family:{FONT_STACK};letter-spacing:0.05em;text-transform:uppercase;
          border:1px solid {mode_br};white-space:nowrap;">{_html.escape(mode_label)}</span>
      </div>
      <p style="margin:0;font-family:{FONT_STACK};font-size:14px;
        line-height:1.65;color:{INK_800};">{intro}</p>
    </td>
  </tr>
</table>

{auto_rotate_notice}
{_metrics_html(records, rotation_enabled)}
{_key_table_html(records, rotation_enabled)}

<div style="margin:22px 0 0 0;padding:14px 18px;border-radius:12px;background-color:{SOFT};
  border:1px solid {LINE};">
  <span style="font-family:{FONT_STACK};font-size:13px;color:{INK_700};">
    Full details in attachment&nbsp;&middot;&nbsp;
    <span style="font-family:{MONO_STACK};font-size:12px;font-weight:600;
      color:{BRAND};background-color:{BRAND_SOFT};padding:4px 10px;border-radius:7px;
      border:1px solid {BRAND_LINE};">{_html.escape(attachment_name)}</span>
  </span>
</div>
""".strip()

    return _wrap_html_email(subject=subject, body_html=content_html)
