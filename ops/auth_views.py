from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.models import User

from .models import AuditLog
from .serializers import UserSerializer


def _log_session_event(action, actor, actor_username, note):
    AuditLog.objects.create(
        actor=actor,
        actor_username=actor_username,
        action=action,
        model_name="Session",
        object_id=str(actor.pk) if actor else "",
        object_repr=note,
    )


class LoginSerializer(TokenObtainPairSerializer):
    """Accepts either a username or an email address in the `username` field."""

    def validate(self, attrs):
        identifier = attrs.get(self.username_field, "")
        match = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        ).first()
        if match:
            attrs[self.username_field] = match.username
        try:
            data = super().validate(attrs)
        except Exception:
            _log_session_event(
                AuditLog.Action.LOGIN_FAILED, None, identifier, f"Failed login attempt as '{identifier}'"
            )
            raise
        data["user"] = UserSerializer(self.user).data
        _log_session_event(AuditLog.Action.LOGIN, self.user, self.user.username, f"{self.user.username} logged in")
        return data


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    user = request.user
    _log_session_event(AuditLog.Action.LOGOUT, user, user.username, f"{user.username} logged out")
    return Response(status=204)
