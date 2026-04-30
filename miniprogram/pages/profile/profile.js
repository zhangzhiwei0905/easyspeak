// pages/profile/profile.js
const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

Page({
  data: {
    userInfo: {},
    stats: {
      studyStreak: 0,
      totalPhrases: 0,
      totalWords: 0,
      totalQuiz: 0,
      avgAccuracy: 0
    },
    achievements: [],
    achievementGroups: []
  },

  onLoad() {
    this.loadUserInfo()
    this.loadStats()
    this.loadAchievements()
  },

  onShow() {
    this.loadStats()
    this.loadUserInfo()
    this.loadAchievements()
  },

  /**
   * Load user info from cache or app globalData
   */
  loadUserInfo() {
    const app = getApp()
    let userInfo = app.globalData.userInfo || storage.get(storage.KEYS.USER_INFO) || {}

    // If no cached info, try getting WeChat user profile
    if (!userInfo.nickName) {
      userInfo = { nickName: '英语学习者', avatarUrl: '' }
    }

    this.setData({ userInfo: userInfo })
  },

  /**
   * Load stats from API, fallback to local storage
   */
  loadStats() {
    var self = this

    api.get('/review/progress/summary')
      .then(function(data) {
        var stats = {
          studyStreak: data.study_streak || data.studyStreak || 0,
          totalPhrases: data.total_phrases || data.totalPhrases || 0,
          totalWords: data.total_words || data.totalWords || 0,
          masteredPhrases: data.mastered_phrases || data.masteredPhrases || 0,
          masteredWords: data.mastered_words || data.masteredWords || 0,
          totalQuiz: data.total_quiz || data.totalQuiz || 0,
          avgAccuracy: data.avg_accuracy || data.avgAccuracy || 0
        }
        self.setData({ stats: stats })
      })
      .catch(function(err) {
        console.warn('[Profile] Failed to load stats from API:', err)
        // Fallback to local data
        self.loadLocalStats()
      })
  },

  /**
   * Load stats from local storage as fallback
   */
  loadLocalStats() {
    var streakDays = storage.getStreakDays() || 0
    var calendar = storage.getStudyCalendar() || []

    var stats = {
      studyStreak: streakDays,
      totalPhrases: 0,
      totalWords: 0,
      totalQuiz: 0,
      avgAccuracy: 0
    }

    // Try to get quiz history for local stats
    var quizHistory = storage.get(storage.KEYS.QUIZ_HISTORY) || []
    if (quizHistory.length > 0) {
      stats.totalQuiz = quizHistory.length
      var correctCount = quizHistory.filter(function(q) { return q.correct }).length
      stats.avgAccuracy = Math.round((correctCount / quizHistory.length) * 100)
    }

    this.setData({ stats: stats })
  },

  /**
   * Load achievements from server, fallback to local cache
   */
  loadAchievements() {
    var self = this
    api.get('/user/achievements')
      .then(function(data) {
        var achievements = (data.achievements || []).map(function(a) {
          if (a.unlocked && a.unlocked_at) {
            var d = new Date(a.unlocked_at)
            a.unlocked_at_display = (d.getMonth() + 1) + '月' + d.getDate() + '日'
          }
          return a
        })
        var groups = self._groupAchievements(achievements)
        self.setData({ achievements: achievements, achievementGroups: groups })
        // Cache for offline fallback
        storage.set(storage.KEYS.ACHIEVEMENTS, achievements)
      })
      .catch(function(err) {
        console.warn('[Profile] Failed to load achievements:', err)
        var cached = storage.get(storage.KEYS.ACHIEVEMENTS) || []
        if (cached.length > 0) {
          var groups = self._groupAchievements(cached)
          self.setData({ achievements: cached, achievementGroups: groups })
        }
      })
  },

  /**
   * Group achievements by category for display
   */
  _groupAchievements(achievements) {
    var categoryOrder = ['learning', 'streak', 'word', 'phrase', 'quiz']
    var groupMap = {}
    achievements.forEach(function(item) {
      var cat = item.category || 'other'
      if (!groupMap[cat]) {
        groupMap[cat] = { category: cat, category_zh: item.category_zh || '', items: [] }
      }
      groupMap[cat].items.push(item)
    })
    return categoryOrder.map(function(cat) { return groupMap[cat] }).filter(Boolean)
  },

  /**
   * Navigate to settings page
   */
  goToSettings() {
    wx.navigateTo({
      url: '/pages/settings/settings'
    })
  },

  /**
   * Allow user to update avatar
   */
  onChooseAvatar() {
    var self = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: function(res) {
        var tempFilePath = res.tempFiles[0].tempFilePath
        // Update local avatar
        var userInfo = self.data.userInfo
        userInfo.avatarUrl = tempFilePath
        self.setData({ userInfo: userInfo })
        storage.set(storage.KEYS.USER_INFO, userInfo)
        var app = getApp()
        if (app) app.globalData.userInfo = userInfo
        wx.showToast({ title: '头像已更新', icon: 'success' })
      },
      fail: function(err) {
        // User cancelled, ignore
        console.log('[Profile] Avatar selection cancelled')
      }
    })
  }
})
