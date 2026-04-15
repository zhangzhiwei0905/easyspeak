const storage = require('./storage')
const api = require('./api')

/**
 * EasySpeak Auth Utilities
 * Handles WeChat login flow: wx.login() → backend /auth/login → store JWT token
 */

/**
 * Perform WeChat login flow
 * 1. Call wx.login() to get a temporary code
 * 2. Send code to backend /auth/login
 * 3. Backend exchanges code for openid via WeChat API
 * 4. Backend returns JWT token
 * 5. Store token locally
 *
 * @returns {Promise<{token: string, user_info: object}>}
 */
function login() {
  return new Promise(function(resolve, reject) {
    wx.login({
      success: function(loginRes) {
        if (!loginRes.code) {
          console.error('[Auth] wx.login() failed: no code returned')
          reject(new Error('wx.login failed: no code'))
          return
        }

        // Send code to backend
        api.post('/auth/login', { code: loginRes.code })
          .then(function(data) {
            if (data && data.token) {
              storage.set(storage.KEYS.TOKEN, data.token)
              if (data.user_info) {
                storage.set(storage.KEYS.USER_INFO, data.user_info)
              }
              console.log('[Auth] Login successful')
              resolve(data)
            } else {
              console.error('[Auth] Login response missing token:', data)
              reject(new Error('登录响应缺少token'))
            }
          })
          .catch(function(err) {
            console.error('[Auth] Backend login failed:', err)
            reject(err)
          })
      },
      fail: function(err) {
        console.error('[Auth] wx.login() failed:', err)
        reject(err)
      }
    })
  })
}

/**
 * Get stored auth token
 * @returns {string|null}
 */
function getToken() {
  return storage.get(storage.KEYS.TOKEN)
}

/**
 * Check if user is logged in (has a non-empty token)
 * @returns {boolean}
 */
function isLoggedIn() {
  var token = getToken()
  return !!(token && token.length > 0)
}

/**
 * Logout — clear token and user info from storage
 */
function logout() {
  storage.remove(storage.KEYS.TOKEN)
  storage.remove(storage.KEYS.USER_INFO)
  console.log('[Auth] User logged out, token cleared')
}

/**
 * Ensure user is logged in before an action.
 * If not logged in, triggers login flow.
 * If already logged in, resolves immediately.
 *
 * @returns {Promise<boolean>} true if logged in successfully
 */
function ensureLogin() {
  if (isLoggedIn()) {
    return Promise.resolve(true)
  }
  return login()
    .then(function() { return true })
    .catch(function(err) {
      console.error('[Auth] ensureLogin failed:', err)
      wx.showToast({
        title: '登录失败，请重试',
        icon: 'none',
        duration: 2000
      })
      return false
    })
}

module.exports = {
  login: login,
  getToken: getToken,
  isLoggedIn: isLoggedIn,
  logout: logout,
  ensureLogin: ensureLogin
}
