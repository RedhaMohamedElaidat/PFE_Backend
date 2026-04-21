# users/permissions.py
from rest_framework.permissions import BasePermission
from users.models import Admin

class IsCustomAdmin(BasePermission):
    """
    Permission qui vérifie si l'utilisateur a un profil Admin personnalisé
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            admin_profile = Admin.objects.get(user=request.user)
            return True
        except Admin.DoesNotExist:
            return False
    
    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsSuperAdmin(BasePermission):
    """
    Permission qui vérifie si l'utilisateur est Super Admin
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            admin_profile = Admin.objects.get(user=request.user)
            return admin_profile.is_super_admin
        except Admin.DoesNotExist:
            return False