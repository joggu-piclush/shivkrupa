/**
 * Shivkrupa Enterprises -- login code mailer (runs on Google Apps Script, under the owner's own Google account).
 *
 * What it does: when the Shivkrupa server asks, it emails a login code from THIS Google account's Gmail.
 * The server makes and checks the code; this script only delivers it. It stores nothing.
 *
 * Safety:
 *   - It can only ever email the addresses listed in ALLOWED_RECIPIENTS below.
 *   - The code must be 4 to 8 digits, and the message text is fixed here, so even if the web address
 *     leaked, the most anyone could do is send a login-code email to those listed people.
 *   - Keep the web address private (it is stored only in the server's settings as GMAIL_RELAY_URL).
 *
 * Gmail's own limit for a normal Google account is about 100 emails a day, far above what logins need.
 */

// Only these addresses can receive a code. Add a new person here, then Deploy > Manage deployments >
// Edit (pencil) > Version: New version > Deploy. The web address stays the same.
var ALLOWED_RECIPIENTS = [
  'PUT-THE-RECEIVER-EMAIL-HERE@gmail.com'
];

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var to = String(data.to || '').trim().toLowerCase();
    var code = String(data.code || '');
    var minutes = Math.max(1, Math.min(30, Number(data.minutes) || 5));

    var allowed = ALLOWED_RECIPIENTS.map(function (a) { return String(a).trim().toLowerCase(); });
    if (allowed.indexOf(to) === -1) return reply_({ ok: false, error: 'recipient not allowed' });
    if (!/^[0-9]{4,8}$/.test(code)) return reply_({ ok: false, error: 'bad code' });

    var text = 'Your Shivkrupa Enterprises login code is ' + code + '\n\n' +
               'It works for ' + minutes + ' minutes. Type it on the sign-in screen.\n\n' +
               'If you did not try to sign in, ignore this email. Never share this code with anyone.\n';
    var html = '<div style="font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:24px;color:#222">' +
               '<p style="margin:0 0 8px">Your Shivkrupa Enterprises login code is</p>' +
               '<p style="font-size:34px;letter-spacing:8px;font-weight:bold;margin:8px 0 16px">' + code + '</p>' +
               '<p style="margin:0 0 8px;color:#555">It works for ' + minutes + ' minutes. Type it on the sign-in screen.</p>' +
               '<p style="margin:0;color:#888;font-size:13px">If you did not try to sign in, ignore this email. ' +
               'Never share this code with anyone.</p></div>';

    MailApp.sendEmail({
      to: to,
      subject: 'Your Shivkrupa Enterprises login code',
      body: text,
      htmlBody: html,
      name: 'Shivkrupa Enterprises'
    });
    return reply_({ ok: true });
  } catch (err) {
    return reply_({ ok: false, error: 'script error' });
  }
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
