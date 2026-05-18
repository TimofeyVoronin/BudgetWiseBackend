from hashlib import sha256

from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        email = request.data.get("email", "")
        email = str(email).strip().lower() or "unknown"

        ident = self.get_ident(request)

        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{ident}:{email}",
        }


class ForgotPasswordIPThrottle(SimpleRateThrottle):
    scope = "forgot_password_ip"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class ForgotPasswordEmailThrottle(SimpleRateThrottle):
    scope = "forgot_password_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email")

        if not isinstance(email, str) or not email.strip():
            return None

        normalized_email = email.strip().lower()
        email_hash = sha256(normalized_email.encode("utf-8")).hexdigest()

        return self.cache_format % {
            "scope": self.scope,
            "ident": email_hash,
        }