const auth = require('./utils/auth')
const storage = require('./utils/storage')

App({
  globalData: {
    // 本地开发: http://localhost:8000/api/v1
    // 服务器部署: https://你的域名/api/v1
    baseUrl: 'https://easyspeak.amazingzz.xyz/api/v1',
    userInfo: null,
    systemInfo: null
  },

  onLaunch() {
    // Ensure iOS plays audio even in silent mode
    if (wx.setInnerAudioOption) {
      wx.setInnerAudioOption({ obeyMuteSwitch: false })
    }

    // Get system info
    const systemInfo = wx.getSystemInfoSync()
    this.globalData.systemInfo = systemInfo

    // Try to load cached user info
    const cachedUserInfo = storage.get(storage.KEYS.USER_INFO)
    if (cachedUserInfo) {
      this.globalData.userInfo = cachedUserInfo
    }

    // Check login status and auto-login
    this.checkLogin()
  },

  onShow(options) {
    // App becomes visible — refresh token if needed
    if (!auth.isLoggedIn()) {
      this.autoLogin()
    }
  },

  onHide() {
    // App hidden
  },

  onError(error) {
    console.error('[App Error]', error)
  },

  /**
   * Check if user is logged in, attempt silent login if not
   */
  checkLogin() {
    if (auth.isLoggedIn()) {
      console.log('[App] User already logged in')
      return
    }
    this.autoLogin()
  },

  /**
   * Silent auto-login via wx.login
   */
  autoLogin() {
    auth.login()
      .then((data) => {
        console.log('[App] Auto-login success')
        if (data && data.user_info) {
          this.globalData.userInfo = data.user_info
          storage.set(storage.KEYS.USER_INFO, data.user_info)
        }
      })
      .catch((err) => {
        console.warn('[App] Auto-login failed:', err)
      })
  },

  /**
   * Update global user info
   */
  setUserInfo(userInfo) {
    this.globalData.userInfo = userInfo
    storage.set(storage.KEYS.USER_INFO, userInfo)
  },

  /**
   * Clear user data on logout
   */
  clearUserData() {
    this.globalData.userInfo = null
    auth.logout()
    storage.remove(storage.KEYS.USER_INFO)
  }
})
