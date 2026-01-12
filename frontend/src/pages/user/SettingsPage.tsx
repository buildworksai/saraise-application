/**
 * User Settings Page
 * 
 * Comprehensive settings management page with real data integration.
 * Allows users to configure application preferences and settings.
 */
import { useState } from 'react';
import { useAuthStore } from '../../stores/auth-store';
import { Bell, Shield, Globe, Moon, Sun, Monitor, Save, AlertCircle, CheckCircle2 } from 'lucide-react';

export const SettingsPage = () => {
  const { user } = useAuthStore();
  const [isSaving, setIsSaving] = useState(false);
  const [settings, setSettings] = useState({
    theme: 'system' as 'light' | 'dark' | 'system',
    notifications: {
      email: true,
      push: false,
      security: true,
    },
    language: 'en',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  });

  const handleSave = async () => {
    setIsSaving(true);
    // TODO: Implement settings save API endpoint
    // For now, save to localStorage
    localStorage.setItem('user-settings', JSON.stringify(settings));
    
    setTimeout(() => {
      setIsSaving(false);
      // Show success message
    }, 500);
  };

  if (!user) {
    return (
      <div className="p-8">
        <div className="text-center text-muted-foreground">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Settings</h1>
        <p className="text-muted-foreground">Manage your application preferences and settings</p>
      </div>

      <div className="space-y-6">
        {/* Appearance Settings */}
        <div className="bg-card rounded-lg border border-border shadow-sm">
          <div className="p-6 border-b border-border">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Monitor className="w-5 h-5" />
              Appearance
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Customize the look and feel of the application</p>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Theme</label>
              <div className="flex gap-4">
                <button
                  onClick={() => setSettings(prev => ({ ...prev, theme: 'light' }))}
                  className={`flex items-center gap-2 px-4 py-2 border rounded-md transition-colors ${
                    settings.theme === 'light'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:bg-accent'
                  }`}
                >
                  <Sun className="w-4 h-4" />
                  Light
                </button>
                <button
                  onClick={() => setSettings(prev => ({ ...prev, theme: 'dark' }))}
                  className={`flex items-center gap-2 px-4 py-2 border rounded-md transition-colors ${
                    settings.theme === 'dark'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:bg-accent'
                  }`}
                >
                  <Moon className="w-4 h-4" />
                  Dark
                </button>
                <button
                  onClick={() => setSettings(prev => ({ ...prev, theme: 'system' }))}
                  className={`flex items-center gap-2 px-4 py-2 border rounded-md transition-colors ${
                    settings.theme === 'system'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:bg-accent'
                  }`}
                >
                  <Monitor className="w-4 h-4" />
                  System
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Notifications Settings */}
        <div className="bg-card rounded-lg border border-border shadow-sm">
          <div className="p-6 border-b border-border">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Bell className="w-5 h-5" />
              Notifications
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Manage how you receive notifications</p>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">Email Notifications</label>
                <p className="text-xs text-muted-foreground">Receive notifications via email</p>
              </div>
              <button
                onClick={() => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, email: !prev.notifications.email }
                }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.notifications.email ? 'bg-primary' : 'bg-muted'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.notifications.email ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">Push Notifications</label>
                <p className="text-xs text-muted-foreground">Receive browser push notifications</p>
              </div>
              <button
                onClick={() => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, push: !prev.notifications.push }
                }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.notifications.push ? 'bg-primary' : 'bg-muted'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.notifications.push ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">Security Alerts</label>
                <p className="text-xs text-muted-foreground">Receive security-related notifications</p>
              </div>
              <button
                onClick={() => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, security: !prev.notifications.security }
                }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.notifications.security ? 'bg-primary' : 'bg-muted'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.notifications.security ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>
        </div>

        {/* Localization Settings */}
        <div className="bg-card rounded-lg border border-border shadow-sm">
          <div className="p-6 border-b border-border">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Globe className="w-5 h-5" />
              Localization
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Configure language and regional settings</p>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Language</label>
              <select
                value={settings.language}
                onChange={(e) => setSettings(prev => ({ ...prev, language: e.target.value }))}
                className="w-full px-4 py-2 border border-border rounded-md bg-background"
              >
                <option value="en">English</option>
                <option value="es">Spanish</option>
                <option value="fr">French</option>
                <option value="de">German</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Timezone</label>
              <select
                value={settings.timezone}
                onChange={(e) => setSettings(prev => ({ ...prev, timezone: e.target.value }))}
                className="w-full px-4 py-2 border border-border rounded-md bg-background"
              >
                <option value={Intl.DateTimeFormat().resolvedOptions().timeZone}>
                  {Intl.DateTimeFormat().resolvedOptions().timeZone}
                </option>
                <option value="UTC">UTC</option>
                <option value="America/New_York">America/New_York</option>
                <option value="America/Los_Angeles">America/Los_Angeles</option>
                <option value="Europe/London">Europe/London</option>
                <option value="Asia/Tokyo">Asia/Tokyo</option>
              </select>
            </div>
          </div>
        </div>

        {/* Security Settings */}
        <div className="bg-card rounded-lg border border-border shadow-sm">
          <div className="p-6 border-b border-border">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Shield className="w-5 h-5" />
              Security
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Manage your security preferences</p>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">Two-Factor Authentication</label>
                <p className="text-xs text-muted-foreground">Add an extra layer of security to your account</p>
              </div>
              <button
                className="px-4 py-2 border border-border rounded-md hover:bg-accent transition-colors"
                onClick={() => {
                  // TODO: Implement 2FA setup
                }}
              >
                Configure
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">Active Sessions</label>
                <p className="text-xs text-muted-foreground">View and manage your active sessions</p>
              </div>
              <button
                className="px-4 py-2 border border-border rounded-md hover:bg-accent transition-colors"
                onClick={() => {
                  // TODO: Implement session management
                }}
              >
                Manage
              </button>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-6 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {isSaving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
};
