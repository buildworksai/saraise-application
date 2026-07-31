export function isProtectedContentBlocked(
  isAuthenticated: boolean,
  isLoading: boolean,
  isSessionVerified: boolean
) {
  return isAuthenticated && (isLoading || !isSessionVerified);
}
