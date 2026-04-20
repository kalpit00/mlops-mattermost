# Mattermost Manifests

This directory contains manifests for the open source service deployment:

- PostgreSQL dependency
- Mattermost application
- Service definitions
- Ingress definition
- Persistent storage claim(s)

Current manifests are starter stubs and will be updated with production-ready values.

## Share with teammates

Public URL matches `MM_SERVICESETTINGS_SITEURL` / Ingress (e.g. `http://129-114-25-58.nip.io`). The deployment sets `MM_TEAMSETTINGS_ENABLEUSERCREATION` and `MM_TEAMSETTINGS_ENABLEOPENSERVER` so people can **create an account** and **join open teams** without a manual invite. For production, tighten these and use SSO or controlled invites.
