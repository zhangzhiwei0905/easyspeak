// pages/settings/settings.js
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

var DEFAULT_SETTINGS = {
  remindEnabled: true,
  morningTime: '09:00',
  eveningTime: '18:00',
  emailPush: false,
  darkMode: false
}

Page({
  data: {
    settings: Object.assign({}, DEFAULT_SETTINGS),
    version: '1.0.0',
    storageSizeText: '计算中...'
  },

  onLoad() {
    this.loadSettings()
    this.calculateStorageSize()
  },

  onShow() {
    // Re-load settings in case dark mode was toggled elsewhere
    this.loadSettings()
  },

  /**
   * Load settings from local storage
   */
  loadSettings() {
    var saved = storage.get(storage.KEYS.SETTINGS)
    var settings = Object.assign({}, DEFAULT_SETTINGS, saved)
    this.setData({ settings: settings })
    this.applyDarkMode(settings.darkMode)
  },

  /**
   * Save current settings to local storage
   */
  saveSettings() {
    storage.set(storage.KEYS.SETTINGS, this.data.settings)
  },

  /**
   * Apply dark mode class to page element
   */
  applyDarkMode(enabled) {
    if (enabled) {
      wx.setNavigationBarColor({
        frontColor: '#ffffff',
        backgroundColor: '#1a1a2e'
      })
    } else {
      wx.setNavigationBarColor({
        frontColor: '#ffffff',
        backgroundColor: '#667eea'
      })
    }
  },

  /**
   * Toggle daily reminder
   */
  onRemindToggle(e) {
    var enabled = e.detail.value
    this.setData({ 'settings.remindEnabled': enabled })
    this.saveSettings()

    if (enabled) {
      wx.showToast({ title: '每日提醒已开启', icon: 'success' })
    } else {
      wx.showToast({ title: '每日提醒已关闭', icon: 'none' })
    }
  },

  /**
   * Change morning reminder time
   */
  onMorningTimeChange(e) {
    this.setData({ 'settings.morningTime': e.detail.value })
    this.saveSettings()
    wx.showToast({ title: '晨间提醒: ' + e.detail.value, icon: 'none' })
  },

  /**
   * Change evening reminder time
   */
  onEveningTimeChange(e) {
    this.setData({ 'settings.eveningTime': e.detail.value })
    this.saveSettings()
    wx.showToast({ title: '晚间提醒: ' + e.detail.value, icon: 'none' })
  },

  /**
   * Toggle email push
   */
  onEmailPushToggle(e) {
    var enabled = e.detail.value
    this.setData({ 'settings.emailPush': enabled })
    this.saveSettings()

    if (enabled) {
      wx.showToast({ title: '邮件推送已开启', icon: 'success' })
    } else {
      wx.showToast({ title: '邮件推送已关闭', icon: 'none' })
    }
  },

  /**
   * Toggle dark mode
   */
  onDarkModeToggle(e) {
    var enabled = e.detail.value
    this.setData({ 'settings.darkMode': enabled })
    this.saveSettings()
    this.applyDarkMode(enabled)

    if (enabled) {
      wx.showToast({ title: '深色模式已开启', icon: 'success' })
    } else {
      wx.showToast({ title: '深色模式已关闭', icon: 'none' })
    }
  },

  /**
   * Show storage info
   */
  showStorageInfo() {
    var info = storage.getStorageInfo()
    var sizeKB = info.currentSize || 0
    var sizeMB = (sizeKB / 1024).toFixed(2)
    var text = sizeKB > 1024 ? sizeMB + ' MB' : sizeKB + ' KB'
    var limitMB = ((info.limitSize || 10240) / 1024).toFixed(0)

    wx.showModal({
      title: '缓存信息',
      content: '已使用: ' + text + '\n限制: ' + limitMB + ' MB\n缓存条目: ' + (info.keys ? info.keys.length : 0) + ' 个',
      showCancel: false,
      confirmText: '知道了'
    })
  },

  /**
   * Calculate and display storage size
   */
  calculateStorageSize() {
    var info = storage.getStorageInfo()
    var sizeKB = info.currentSize || 0
    var text = sizeKB > 1024 ? (sizeKB / 1024).toFixed(1) + ' MB' : sizeKB + ' KB'
    this.setData({ storageSizeText: text })
  },

  /**
   * Clear all cached data
   */
  onClearCache() {
    var self = this
    wx.showModal({
      title: '清除缓存',
      content: '确定要清除所有本地缓存数据吗？此操作不可撤销。',
      confirmColor: '#ff4d4f',
      confirmText: '确定清除',
      success: function(res) {
        if (res.confirm) {
          // Clear all EasySpeak storage except settings and auth token
          storage.clearAll()
          // Re-save settings
          storage.set(storage.KEYS.SETTINGS, self.data.settings)

          self.calculateStorageSize()
          wx.showToast({ title: '缓存已清除', icon: 'success' })
        }
      }
    })
  },

  /**
   * Logout
   */
  onLogout() {
    var self = this
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      confirmColor: '#ff4d4f',
      confirmText: '退出',
      success: function(res) {
        if (res.confirm) {
          auth.logout()
          var app = getApp()
          if (app) {
            app.clearUserData()
          }
          wx.showToast({ title: '已退出登录', icon: 'success' })
          // Navigate back to profile
          setTimeout(function() {
            wx.navigateBack()
          }, 1000)
        }
      }
    })
  }
})
