/**
 * User Profile Page
 * 
 * Comprehensive profile management page with real data integration.
 * Allows users to view and update their profile information.
 */
import { useState } from 'react';
import { useAuthStore } from '../../stores/auth-store';
import { authService } from '../../services/auth-service';
import { apiClient } from '../../services/api-client';
import { User, Mail, Key, Save, X, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

export const ProfilePage = () => {
  const { user, setUser } = useAuthStore();
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.username.trim()) {
      newErrors.username = 'Username is required';
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Invalid email format';
    }

    if (formData.newPassword) {
      if (formData.newPassword.length < 8) {
        newErrors.newPassword = 'Password must be at least 8 characters';
      }
      if (formData.newPassword !== formData.confirmPassword) {
        newErrors.confirmPassword = 'Passwords do not match';
      }
      if (!formData.currentPassword) {
        newErrors.currentPassword = 'Current password is required to change password';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validateForm()) {
      toast.error('Please fix the errors before saving');
      return;
    }

    setIsSaving(true);
    try {
      const updateData: Record<string, string> = {};
      
      if (formData.username !== user?.username) {
        updateData.username = formData.username;
      }
      
      if (formData.email !== user?.email) {
        updateData.email = formData.email;
      }
      
      if (formData.newPassword) {
        updateData.password = formData.newPassword;
        updateData.current_password = formData.currentPassword;
      }

      const response = await apiClient.patch('/api/v1/auth/profile/', updateData);
      
      // Update user in store
      if (response.user) {
        setUser(response.user);
      }

      // Reset password fields
      setFormData(prev => ({
        ...prev,
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      }));

      setIsEditing(false);
      toast.success('Your profile has been successfully updated');
    } catch (error: any) {
      const errorMessage = error.response?.data?.error || 'Failed to update profile';
      toast.error(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setFormData({
      username: user?.username || '',
      email: user?.email || '',
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    });
    setErrors({});
    setIsEditing(false);
  };

  if (!user) {
    return (
      <div className="p-8">
        <div className="text-center text-muted-foreground">Loading profile...</div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Profile</h1>
        <p className="text-muted-foreground">Manage your account information and preferences</p>
      </div>

      <div className="bg-card rounded-lg border border-border shadow-sm">
        {/* Profile Header */}
        <div className="p-6 border-b border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 bg-primary rounded-full flex items-center justify-center text-primary-foreground text-2xl font-bold">
                {user.username?.[0]?.toUpperCase() || user.email[0].toUpperCase()}
              </div>
              <div>
                <h2 className="text-xl font-semibold">{user.username || user.email}</h2>
                <p className="text-sm text-muted-foreground">{user.email}</p>
                {user.tenant_role && (
                  <span className="inline-block mt-1 px-2 py-1 text-xs bg-primary/10 text-primary rounded-md">
                    {user.tenant_role.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </span>
                )}
              </div>
            </div>
            {!isEditing && (
              <button
                onClick={() => setIsEditing(true)}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
              >
                Edit Profile
              </button>
            )}
          </div>
        </div>

        {/* Profile Form */}
        <div className="p-6 space-y-6">
          {/* Username */}
          <div>
            <label className="block text-sm font-medium mb-2 flex items-center gap-2">
              <User className="w-4 h-4" />
              Username
            </label>
            {isEditing ? (
              <div>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData(prev => ({ ...prev, username: e.target.value }))}
                  className={`w-full px-4 py-2 border rounded-md bg-background ${
                    errors.username ? 'border-destructive' : 'border-border'
                  }`}
                  placeholder="Enter username"
                />
                {errors.username && (
                  <p className="mt-1 text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {errors.username}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground">{user.username || 'Not set'}</p>
            )}
          </div>

          {/* Email */}
          <div>
            <label className="block text-sm font-medium mb-2 flex items-center gap-2">
              <Mail className="w-4 h-4" />
              Email
            </label>
            {isEditing ? (
              <div>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
                  className={`w-full px-4 py-2 border rounded-md bg-background ${
                    errors.email ? 'border-destructive' : 'border-border'
                  }`}
                  placeholder="Enter email"
                />
                {errors.email && (
                  <p className="mt-1 text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {errors.email}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground">{user.email}</p>
            )}
          </div>

          {/* Password Change Section */}
          {isEditing && (
            <div className="pt-6 border-t border-border space-y-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Key className="w-5 h-5" />
                Change Password
              </h3>
              
              <div>
                <label className="block text-sm font-medium mb-2">Current Password</label>
                <input
                  type="password"
                  value={formData.currentPassword}
                  onChange={(e) => setFormData(prev => ({ ...prev, currentPassword: e.target.value }))}
                  className={`w-full px-4 py-2 border rounded-md bg-background ${
                    errors.currentPassword ? 'border-destructive' : 'border-border'
                  }`}
                  placeholder="Enter current password"
                />
                {errors.currentPassword && (
                  <p className="mt-1 text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {errors.currentPassword}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">New Password</label>
                <input
                  type="password"
                  value={formData.newPassword}
                  onChange={(e) => setFormData(prev => ({ ...prev, newPassword: e.target.value }))}
                  className={`w-full px-4 py-2 border rounded-md bg-background ${
                    errors.newPassword ? 'border-destructive' : 'border-border'
                  }`}
                  placeholder="Enter new password (leave blank to keep current)"
                />
                {errors.newPassword && (
                  <p className="mt-1 text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {errors.newPassword}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Confirm New Password</label>
                <input
                  type="password"
                  value={formData.confirmPassword}
                  onChange={(e) => setFormData(prev => ({ ...prev, confirmPassword: e.target.value }))}
                  className={`w-full px-4 py-2 border rounded-md bg-background ${
                    errors.confirmPassword ? 'border-destructive' : 'border-border'
                  }`}
                  placeholder="Confirm new password"
                />
                {errors.confirmPassword && (
                  <p className="mt-1 text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {errors.confirmPassword}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Account Information (Read-only) */}
          <div className="pt-6 border-t border-border space-y-4">
            <h3 className="text-lg font-semibold">Account Information</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1 text-muted-foreground">User ID</label>
                <p className="text-sm">{user.id}</p>
              </div>
              {user.tenant_id && (
                <div>
                  <label className="block text-sm font-medium mb-1 text-muted-foreground">Tenant ID</label>
                  <p className="text-sm font-mono">{user.tenant_id}</p>
                </div>
              )}
              {user.tenant_role && (
                <div>
                  <label className="block text-sm font-medium mb-1 text-muted-foreground">Role</label>
                  <p className="text-sm capitalize">{user.tenant_role.replace('_', ' ')}</p>
                </div>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          {isEditing && (
            <div className="flex items-center gap-4 pt-6 border-t border-border">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="flex items-center gap-2 px-6 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {isSaving ? 'Saving...' : 'Save Changes'}
              </button>
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className="flex items-center gap-2 px-6 py-2 border border-border rounded-md hover:bg-accent transition-colors disabled:opacity-50"
              >
                <X className="w-4 h-4" />
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
