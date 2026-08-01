export function isProtectedContentBlocked(
  _isAuthenticated: boolean,
  isLoading: boolean,
  isSessionVerified: boolean
) {
  return isLoading || !isSessionVerified;
}
