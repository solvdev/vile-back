from rest_framework import serializers
from .models import CustomUser, Client
from studio.serializers import MembershipSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from studio.models import Membership

class CustomUserSerializer(serializers.ModelSerializer):
    groups = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'groups']

    def get_groups(self, obj):
        return [group.name for group in obj.groups.all()]


class ClientSerializer(serializers.ModelSerializer):
    active_membership = serializers.SerializerMethodField()
    current_membership = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = '__all__'
        extra_kwargs = {
            'email': {'required': False},
            'first_name': {'required': False},
            'last_name': {'required': False},
            'status': {'required': False},
            'age': {'required': False, 'allow_null': True},
        }

    def get_active_membership(self, obj):
        if obj.active_membership:
            return MembershipSerializer(obj.active_membership).data
        return None
    
    def get_current_membership(self, obj):
        if obj.current_membership:
            from studio.serializers import MembershipSerializer
            return MembershipSerializer(obj.current_membership).data
        return None
    

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['groups'] = [group.name for group in user.groups.all()]
        return token
