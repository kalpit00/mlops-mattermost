# Mattermost Manifests

This directory contains manifests for the open source service deployment:

- PostgreSQL dependency
- Mattermost application
- Service definitions
- Ingress definition
- Persistent storage claim(s)

Current manifests are starter stubs and will be updated with production-ready values.

## Share with teammates

**URL to share:** same as `MM_SERVICESETTINGS_SITEURL` / Ingress (e.g. `http://129-114-25-58.nip.io`). Direct signup page: `http://129-114-25-58.nip.io/signup_user_complete` (replace host if your FIP/nip.io changes).

Manifests set open signup and **no email verification** (no SMTP on this stack). There is **no** one-user limit in Team Edition; if only you exist, it is almost always **team access**, not global config.

### A. Let anyone with an account join your team (simplest for class)

The **server** allows open signup (`Enable Open Server`). Each **team** must also allow public join:

1. In Mattermost, open the **team menu** (click the team name / hamburger beside it).
2. Choose **Team Settings** (or **Settings** → team).
3. Turn on **Allow anyone to join the team** / **Allow open invites** (wording varies by version; it sets `allow_open_invite` on the team).
4. Teammates: open the site URL → **Create account** → after signup they can **browse open teams** and join yours.

If you do not see that toggle, use **Invite link** (below).

### B. Invite link (works without SMTP)

Email invites often **fail** until SMTP is configured. Use a **link** instead:

1. **Main menu** (≡) → **Invite People** (or team menu → **Invite people**).
2. Open the **Invite members** dialog and use **Copy invite link** / **Copy link** (not “Send invite email”).
3. Teammates open that link in a **private/incognito** window and complete signup.

### C. You still look “logged in” as the old user

Use **Profile menu → Log out**, or clear site data for the nip.io host, or an incognito window when testing a second account.

### D. Sanity-check what the server advertises (from laptop or VM)

```bash
curl -sS 'http://129-114-25-58.nip.io/api/v4/config/client' | grep -E 'EnableSignUpWithEmail|EnableOpenServer|EnableUserCreation|EnableDeveloper'
```

You should see signup-related flags `true` where expected. If not, confirm the pod picked up the latest Deployment (`kubectl -n mattermost describe deploy mattermost`).

For production, tighten signup settings and use SSO or controlled invites.
