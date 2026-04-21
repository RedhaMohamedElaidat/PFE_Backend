# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.views import (
    RegisterView,  # Maintenant c'est un APIView
    ChangePasswordView,
    UserViewSet,
    ResearcherViewSet,
    AdminViewSet,
    LabManagerViewSet,
    TeamLeaderViewSet,
    InstitutionDirectorViewSet,
    PasswordResetRequestView,
    PasswordResetConfirmView,

    upgrade_to_researcher,
    TeamLeaderCheckView,
    get_all_researchers,
    lab_manager_check,
    lab_manager_login,
    institution_director_check,
    institution_login,
    admin_check,
    admin_dashboard_stats,
    admin_institutions,
    admin_laboratories,
    admin_researchers,
    admin_publications,
    admin_teams,
    admin_users,
    
    
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'researchers', ResearcherViewSet, basename='researcher')
router.register(r'admins', AdminViewSet, basename='admin')
router.register(r'lab-managers', LabManagerViewSet, basename='lab-manager')
router.register(r'team-leaders', TeamLeaderViewSet, basename='team-leader')
router.register(r'institution-directors', InstitutionDirectorViewSet, basename='institution-director')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('upgrade-to-researcher/', upgrade_to_researcher, name='upgrade_to_researcher'),
    path('check-team-leader/', TeamLeaderCheckView.as_view(), name='check_team_leader'),
    path('researchers/all/', get_all_researchers, name='get_all_researchers'),
    path('lab-manager-check/', lab_manager_check, name='lab_manager_check'),
    path('lab-manager-login/', lab_manager_login, name='lab_manager_login'),
    path('institution-director-check/', institution_director_check, name='institution_director_check'),
    path('institution-login/', institution_login, name='institution_login'),
    path('admin-check/', admin_check, name='admin-check'), 
    path('admin/dashboard/stats/', admin_dashboard_stats, name='admin-dashboard-stats'),
    path('admin/institutions/', admin_institutions, name='admin-institutions'),
    path('admin/institutions/<int:institution_id>/', admin_institutions, name='admin-institution-detail'),
    path('admin/laboratories/', admin_laboratories, name='admin-laboratories'),
    path('admin/laboratories/<int:lab_id>/', admin_laboratories, name='admin-laboratory-detail'),
    path('admin/laboratories/<int:lab_id>/teams/', admin_laboratories, name='admin-laboratory-teams'),
    path('admin/laboratories/<int:lab_id>/members/', admin_laboratories, name='admin-laboratory-members'),
    path('admin/teams/', admin_teams, name='admin-teams'),
    path('admin/teams/<int:team_id>/', admin_teams, name='admin-team-detail'),
    path('admin/teams/<int:team_id>/members/', admin_teams, name='admin-team-members'),
    path('admin/researchers/', admin_researchers, name='admin-researchers'),
    path('admin/researchers/<int:researcher_id>/', admin_researchers, name='admin-researcher-detail'),
    path('admin/researchers/<int:researcher_id>/publications/', admin_researchers, name='admin-researcher-publications'),
    path('admin/publications/', admin_publications, name='admin-publications'),
    path('admin/publications/<int:pub_id>/', admin_publications, name='admin-publication-detail'),
    path('admin/users/', admin_users, name='admin-users'),
    path('admin/users/<int:user_id>/', admin_users, name='admin-user-detail'),


    path('', include(router.urls)),
]