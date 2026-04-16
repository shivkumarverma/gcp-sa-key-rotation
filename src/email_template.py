"""
HTML email body builder for key scan and rotation reports.
Matches the FinOps email style used in the billing project (inline CSS, blue gradient header).
"""

from __future__ import annotations

import html as _html

from src.rotator import RotationRecord


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _auto_notice_text() -> str:
    return (
        "This is an automatically generated email. For questions or concerns, "
        "please contact the DevOps / Cloud Ops team."
    )


def _wrap_html_email(*, subject: str, body_html: str) -> str:
    subj = _html.escape(subject or "", quote=False)
    notice = _html.escape(_auto_notice_text(), quote=False)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light" />
    <title>{subj}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#EEF2F6;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="border-collapse:collapse;background-color:#EEF2F6;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="680" cellspacing="0" cellpadding="0" border="0"
            style="border-collapse:collapse;max-width:680px;width:100%;">
            <tr>
              <td style="padding:0;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                  style="border-collapse:collapse;background-color:#FFFFFF;border:1px solid #E4E7EC;
                  border-radius:16px;overflow:hidden;box-shadow:0 8px 32px rgba(15,23,42,0.08);">
                  <!-- Header -->
                  <tr>
                    <td style="padding:0;background-color:#175CD3;
                      background-image:linear-gradient(135deg,#1240A8 0%,#2563EB 55%,#3B82F6 100%);">
                      <div style="padding:22px 24px;font-family:Segoe UI,Roboto,Arial,sans-serif;">
                        <div style="font-size:11px;font-weight:600;letter-spacing:0.12em;
                          text-transform:uppercase;color:#BFDBFE;margin-bottom:8px;">Cloud Ops</div>
                        <div style="font-size:20px;font-weight:700;line-height:1.25;color:#FFFFFF;
                          letter-spacing:-0.02em;">GCP Service Account Key Report</div>
                        <div style="margin-top:8px;font-size:13px;color:#DBEAFE;line-height:1.45;">
                          Automated key expiry scan and rotation summary
                        </div>
                      </div>
                    </td>
                  </tr>
                  <!-- Title -->
                  <tr>
                    <td style="padding:22px 24px 8px 24px;background-color:#FFFFFF;">
                      <div style="font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:17px;
                        font-weight:700;line-height:1.35;color:#101828;letter-spacing:-0.02em;">
                        {subj}
                      </div>
                      <div style="margin-top:8px;height:3px;width:48px;border-radius:2px;
                        background:linear-gradient(90deg,#175CD3,#60A5FA);"></div>
                    </td>
                  </tr>
                  <!-- Body -->
                  <tr>
                    <td style="padding:8px 24px 24px 24px;background-color:#FFFFFF;">
                      <div style="font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:14px;
                        line-height:1.6;color:#344054;">
                        {body_html}
                      </div>
                    </td>
                  </tr>
                  <!-- Footer notice -->
                  <tr>
                    <td style="padding:18px 24px;background-color:#F9FAFB;border-top:1px solid #E5E7EB;">
                      <div style="font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:12px;
                        line-height:1.55;color:#667085;">
                        <span style="display:inline-block;padding:2px 8px;border-radius:6px;
                          background-color:#EFF4FF;color:#175CD3;font-weight:600;font-size:11px;
                          margin-right:6px;">Auto</span>
                        <strong style="color:#475467;">Notice:</strong> {notice}
                      </div>
                    </td>
                  </tr>
                </table>
                <div style="margin-top:16px;font-family:Segoe UI,Roboto,Arial,sans-serif;
                  font-size:11px;color:#98A2B3;text-align:center;line-height:1.5;">
                  This message was sent automatically. Please do not reply.
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
    expiring = sum(1 for r in records if r.status == "Expiring")
    rotated = sum(1 for r in records if r.status == "Rotated")
    errors = sum(1 for r in records if r.status == "Error")
    ok = sum(1 for r in records if r.status == "OK")

    label = (
        "font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.07em;"
        "color:#667085;font-family:Segoe UI,Roboto,Arial,sans-serif;margin-bottom:8px;"
    )
    val = (
        "font-size:22px;font-weight:800;color:#101828;"
        "font-family:Segoe UI,Roboto,Arial,sans-serif;letter-spacing:-0.03em;"
    )
    val_warn = val.replace("#101828", "#B45309")  # amber for expiring
    val_err = val.replace("#101828", "#B91C1C")   # red for errors
    val_ok = val.replace("#101828", "#15803D")    # green for ok/rotated

    if rotation_enabled:
        cells = [
            ("Keys Checked", str(total), val),
            ("Rotated", str(rotated), val_ok),
            ("Errors", str(errors), val_err if errors else val),
            ("No Action Needed", str(ok), val),
        ]
    else:
        cells = [
            ("Keys Checked", str(total), val),
            ("Expiring (&le;threshold)", str(expiring), val_warn if expiring else val),
            ("Safe / OK", str(ok), val_ok),
            ("Errors", str(errors), val_err if errors else val),
        ]

    td_style = "padding:14px 16px;border-right:1px solid #E4E7EC;vertical-align:top;"
    tds = ""
    for i, (lbl, v, v_style) in enumerate(cells):
        border = "" if i == len(cells) - 1 else "border-right:1px solid #E4E7EC;"
        tds += (
            f'<td style="padding:14px 18px;{border}vertical-align:top;">'
            f'<div style="{label}">{_html.escape(lbl)}</div>'
            f'<div style="{v_style}">{v}</div>'
            f'</td>'
        )

    return f"""
<div style="margin:0 0 20px 0;padding:4px;border-radius:14px;background-color:#FCFCFD;
  border:1px solid #E4E7EC;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
    style="border-collapse:collapse;">
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
        "padding:10px 12px;font-size:10px;font-weight:800;text-transform:uppercase;"
        "letter-spacing:0.08em;color:#FFFFFF;font-family:Segoe UI,Roboto,Arial,sans-serif;"
        "background-color:#1D4ED8;"
    )

    if rotation_enabled:
        display_records = [r for r in records if r.status in ("Rotated", "Error")]
        headers = ["Service Account", "Project", "Expiry Date", "Days Left", "Status"]
    else:
        display_records = records
        headers = ["Service Account", "Project", "Expiry Date", "Days Remaining", "Status"]

    display_records = display_records[:5]

    if not display_records:
        msg = "No keys require attention." if rotation_enabled else "No keys found."
        return f'<p style="color:#667085;font-size:14px;font-family:Segoe UI,Roboto,Arial,sans-serif;">{msg}</p>'

    header_row = "".join(f'<th style="{th}">{h}</th>' for h in headers)

    status_colours = {
        "Rotated":  ("#15803D", "#F0FDF4"),
        "OK":       ("#15803D", "#F0FDF4"),
        "Expiring": ("#92400E", "#FFFBEB"),
        "Error":    ("#B91C1C", "#FEF2F2"),
    }

    td_base = (
        "padding:10px 12px;font-size:13px;font-family:Segoe UI,Roboto,Arial,sans-serif;"
        "border-bottom:1px solid #E8ECF2;vertical-align:middle;"
    )

    body_rows = []
    for i, rec in enumerate(display_records):
        bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
        expiry_str = rec.expiry_date.strftime("%Y-%m-%d") if rec.expiry_date else "N/A"
        days_str = str(rec.days_remaining) if rec.days_remaining is not None else "N/A"
        status_color, status_bg = status_colours.get(rec.status, ("#374151", "#F3F4F6"))

        status_badge = (
            f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
            f'background-color:{status_bg};color:{status_color};font-weight:700;font-size:12px;">'
            f'{_html.escape(rec.status)}</span>'
        )

        cells = [
            _html.escape(rec.sa_email),
            _html.escape(rec.project_name or rec.project_id),
            _html.escape(expiry_str),
            _html.escape(days_str),
            status_badge,
        ]

        tds = "".join(
            f'<td style="{td_base}background-color:{bg};">{c}</td>' for c in cells
        )
        body_rows.append(f'<tr>{tds}</tr>')

    total = len([r for r in records if r.status in ("Rotated", "Error")] if rotation_enabled else records)
    overflow_note = (
        f'<tr><td colspan="{len(headers)}" style="padding:10px 12px;font-size:12px;'
        f'color:#667085;font-family:Segoe UI,Roboto,Arial,sans-serif;background-color:#F9FAFB;">'
        f'Showing 5 of {total} — see attachment for full list.</td></tr>'
        if total > 5 else ""
    )

    return f"""
<div style="margin:20px 0 0 0;border-radius:14px;overflow:hidden;border:1px solid #D8DEE6;
  box-shadow:0 4px 16px rgba(15,23,42,0.06);">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
    style="border-collapse:collapse;">
    <thead>
      <tr>
        <th colspan="{len(headers)}" align="left"
          style="padding:16px 18px;background-color:#175CD3;
          background-image:linear-gradient(135deg,#1547A0 0%,#2E6FE0 100%);">
          <span style="font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:14px;
            font-weight:700;color:#FFFFFF;letter-spacing:-0.02em;">
            {"Key Rotation Results" if rotation_enabled else "Key Expiry Scan Results"}
          </span>
          <span style="display:block;margin-top:4px;font-size:12px;font-weight:400;
            color:#C7D7FE;font-family:Segoe UI,Roboto,Arial,sans-serif;">
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
    mode_badge_color = "#15803D" if rotation_enabled else "#1D4ED8"
    mode_badge_bg = "#F0FDF4" if rotation_enabled else "#EFF4FF"

    intro = (
        "The attached Excel workbook contains the full results for all projects. "
        "Keys marked <strong>Expiring</strong> are within the alert threshold and require attention."
        if not rotation_enabled else
        "New key files have been generated and stored. "
        "Please verify the new credentials before retiring the old keys. "
        "Old keys have <strong>not</strong> been deleted automatically."
    )

    content_html = f"""
<p style="margin:0 0 16px 0;font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:16px;
  font-weight:600;color:#101828;">Hi Team,</p>
<div style="margin:0 0 18px 0;padding:14px 18px;border-radius:12px;background-color:#F8FAFF;
  border:1px solid #E0E7FF;border-left:4px solid #175CD3;display:flex;align-items:center;gap:12px;">
  <span style="display:inline-block;padding:3px 10px;border-radius:10px;
    background-color:{mode_badge_bg};color:{mode_badge_color};font-weight:700;
    font-size:12px;font-family:Segoe UI,Roboto,Arial,sans-serif;white-space:nowrap;">
    {_html.escape(mode_label)}
  </span>
  <p style="margin:0;font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:14px;
    line-height:1.65;color:#1D2939;">{intro}</p>
</div>
{_metrics_html(records, rotation_enabled)}
{_key_table_html(records, rotation_enabled)}
<div style="margin:18px 0 0 0;padding:12px 16px;border-radius:10px;background-color:#F9FAFB;
  border:1px solid #E4E7EC;">
  <span style="font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:13px;color:#475467;">
    Full details in attachment:&nbsp;
    <span style="font-family:ui-monospace,Consolas,monospace;font-size:12px;font-weight:600;
      color:#175CD3;background-color:#EFF4FF;padding:3px 8px;border-radius:6px;
      border:1px solid #C7D7FE;">{_html.escape(attachment_name)}</span>
  </span>
</div>
""".strip()

    return _wrap_html_email(subject=subject, body_html=content_html)
