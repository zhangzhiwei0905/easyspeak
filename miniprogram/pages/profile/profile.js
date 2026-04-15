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
    achievements: [
      { id: 'beginner', icon: '🌟', name: '初学者', desc: '完成首次学习', unlocked: false },
      { id: 'week_streak', icon: '📅', name: '7日打卡', desc: '连续学习7天', unlocked: false },
      { id: 'study_freak', icon: '🔥', name: '学习狂人', desc: '连续学习30天', unlocked: false },
      { id: 'word_master', icon: '📚', name: '百词斩', desc: '掌握100个单词', unlocked: false },
      { id: 'quiz_expert', icon: '🎯', name: '答题达人', desc: '答题正确率80%+', unlocked: false },
      { id: 'phrase_collector', icon: '💬', name: '短语收藏家', desc: '掌握50个短语', unlocked: false }
    ]
  },

  onLoad() {
    this.loadUserInfo()
    this.loadStats()
  },

  onShow() {
    // Refresh stats every time page is shown
    this.loadStats()
    this.loadUserInfo()
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

    api.get('/progress/summary')
      .then(function(data) {
        var stats = {
          studyStreak: data.study_streak || data.studyStreak || 0,
          totalPhrases: data.total_phrases || data.totalPhrases || 0,
          totalWords: data.total_words || data.totalWords || 0,
          totalQuiz: data.total_quiz || data.totalQuiz || 0,
          avgAccuracy: data.avg_accuracy || data.avgAccuracy || 0
        }
        self.setData({ stats: stats })
        self.updateAchievements(stats)
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
    this.updateAchievements(stats)
  },

  /**
   * Update achievement unlock status based on stats
   */
  updateAchievements(stats) {
    var achievements = this.data.achievements

    achievements.forEach(function(item) {
      switch (item.id) {
        case 'beginner':
          item.unlocked = stats.totalPhrases > 0 || stats.totalWords > 0
          break
        case 'week_streak':
          item.unlocked = stats.studyStreak >= 7
          break
        case 'study_freak':
          item.unlocked = stats.studyStreak >= 30
          break
        case 'word_master':
          item.unlocked = stats.totalWords >= 100
          break
        case 'quiz_expert':
          item.unlocked = stats.totalQuiz > 0 && stats.avgAccuracy >= 80
          break
        case 'phrase_collector':
          item.unlocked = stats.totalPhrases >= 50
          break
      }
    })

    this.setData({ achievements: achievements })
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
