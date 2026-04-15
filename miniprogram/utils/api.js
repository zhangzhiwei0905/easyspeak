const storage = require('./storage')
const auth = require('./auth')

/**
 * EasySpeak API Request Wrapper
 * Handles auth, error display, and response parsing
 */

const DEFAULT_CONFIG = {
  baseUrl: 'http://localhost:8000/api/v1',
  timeout: 15000,
  contentType: 'application/json'
}

let globalConfig = Object.assign({}, DEFAULT_CONFIG)

/**
 * Set custom base URL (for different environments)
 */
function setBaseUrl(url) {
  globalConfig.baseUrl = url
}

/**
 * Get current base URL
 */
function getBaseUrl() {
  const app = getApp()
  return (app && app.globalData && app.globalData.baseUrl) || globalConfig.baseUrl
}

/**
 * Build full URL from path and params
 */
function buildUrl(url, params) {
  let fullUrl = ''
  if (url.startsWith('http://') || url.startsWith('https://')) {
    fullUrl = url
  } else {
    fullUrl = getBaseUrl() + url
  }

  if (params && typeof params === 'object') {
    const queryString = Object.keys(params)
      .filter(key => params[key] !== undefined && params[key] !== null && params[key] !== '')
      .map(key => encodeURIComponent(key) + '=' + encodeURIComponent(params[key]))
      .join('&')
    if (queryString) {
      fullUrl += (fullUrl.indexOf('?') === -1 ? '?' : '&') + queryString
    }
  }

  return fullUrl
}

/**
 * Request interceptor — add auth headers before sending
 */
function requestInterceptor(header) {
  const newHeader = Object.assign({
    'Content-Type': globalConfig.contentType
  }, header)

  const token = storage.get(storage.KEYS.TOKEN)
  if (token) {
    newHeader['Authorization'] = 'Bearer ' + token
  }

  return newHeader
}

/**
 * Response interceptor — handle common errors
 */
function responseInterceptor(res) {
  const statusCode = res.statusCode

  if (statusCode >= 200 && statusCode < 300) {
    return Promise.resolve(res.data)
  }

  // Handle specific error codes
  switch (statusCode) {
    case 401:
      // Token expired or invalid — attempt re-login
      console.warn('[API] 401 Unauthorized, attempting re-login...')
      auth.login()
        .then(() => {
          console.log('[API] Re-login success, but original request not retried automatically')
        })
        .catch((err) => {
          console.error('[API] Re-login failed:', err)
        })
      wx.showToast({
        title: '登录已过期，请重试',
        icon: 'none',
        duration: 2000
      })
      return Promise.reject({ code: 401, message: '登录已过期' })

    case 403:
      wx.showToast({
        title: '没有权限访问',
        icon: 'none',
        duration: 2000
      })
      return Promise.reject({ code: 403, message: '没有权限' })

    case 404:
      wx.showToast({
        title: '请求的资源不存在',
        icon: 'none',
        duration: 2000
      })
      return Promise.reject({ code: 404, message: '资源不存在' })

    case 422:
      // Validation error from backend
      const msg = (res.data && res.data.detail) || '请求参数有误'
      wx.showToast({
        title: msg,
        icon: 'none',
        duration: 2500
      })
      return Promise.reject({ code: 422, message: msg, data: res.data })

    case 429:
      wx.showToast({
        title: '请求过于频繁，请稍后重试',
        icon: 'none',
        duration: 2000
      })
      return Promise.reject({ code: 429, message: '请求过于频繁' })

    case 500:
    case 502:
    case 503:
      wx.showToast({
        title: '服务器异常，请稍后重试',
        icon: 'none',
        duration: 2000
      })
      return Promise.reject({ code: statusCode, message: '服务器异常' })

    default:
      const defaultMsg = (res.data && res.data.message) || (res.data && res.data.detail) || '请求失败'
      wx.showToast({
        title: defaultMsg,
        icon: 'none',
        duration: 2000
      })
      return Promise.reject({ code: statusCode, message: defaultMsg })
  }
}

/**
 * Core request function
 */
function request(url, options) {
  options = options || {}

  const method = (options.method || 'GET').toUpperCase()
  const params = options.params || null
  const data = options.data || null
  const header = options.header || {}
  const timeout = options.timeout || globalConfig.timeout

  const fullUrl = buildUrl(url, params)
  const finalHeader = requestInterceptor(header)

  return new Promise(function(resolve, reject) {
    wx.request({
      url: fullUrl,
      method: method,
      data: data,
      header: finalHeader,
      timeout: timeout,
      success: function(res) {
        responseInterceptor(res)
          .then(resolve)
          .catch(reject)
      },
      fail: function(err) {
        console.error('[API] Request failed:', err)
        if (err.errMsg && err.errMsg.indexOf('timeout') !== -1) {
          wx.showToast({
            title: '请求超时，请检查网络',
            icon: 'none',
            duration: 2000
          })
          reject({ code: -1, message: '请求超时' })
        } else {
          wx.showToast({
            title: '网络连接失败',
            icon: 'none',
            duration: 2000
          })
          reject({ code: -2, message: '网络连接失败' })
        }
      }
    })
  })
}

/**
 * GET request
 * @param {string} url - API path (e.g., '/daily/today')
 * @param {object} params - Query parameters
 * @param {object} options - Additional options (header, timeout)
 */
function get(url, params, options) {
  options = Object.assign({}, options, {
    method: 'GET',
    params: params
  })
  return request(url, options)
}

/**
 * POST request
 * @param {string} url - API path
 * @param {object} data - Request body
 * @param {object} options - Additional options
 */
function post(url, data, options) {
  options = Object.assign({}, options, {
    method: 'POST',
    data: data
  })
  return request(url, options)
}

/**
 * PUT request
 * @param {string} url - API path
 * @param {object} data - Request body
 * @param {object} options - Additional options
 */
function put(url, data, options) {
  options = Object.assign({}, options, {
    method: 'PUT',
    data: data
  })
  return request(url, options)
}

/**
 * DELETE request
 * @param {string} url - API path
 * @param {object} params - Query parameters
 * @param {object} options - Additional options
 */
function del(url, params, options) {
  options = Object.assign({}, options, {
    method: 'DELETE',
    params: params
  })
  return request(url, options)
}

/**
 * Upload file
 * @param {string} url - API path
 * @param {string} filePath - Local file path
 * @param {string} name - File field name
 * @param {object} formData - Additional form data
 */
function upload(url, filePath, name, formData) {
  const fullUrl = buildUrl(url, null)
  const header = requestInterceptor({})
  // Remove Content-Type for upload — wx will set it with boundary automatically
  delete header['Content-Type']

  return new Promise(function(resolve, reject) {
    wx.uploadFile({
      url: fullUrl,
      filePath: filePath,
      name: name || 'file',
      header: header,
      formData: formData || {},
      success: function(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(res.data))
          } catch (e) {
            resolve(res.data)
          }
        } else {
          responseInterceptor(res).then(resolve).catch(reject)
        }
      },
      fail: function(err) {
        console.error('[API] Upload failed:', err)
        wx.showToast({
          title: '上传失败',
          icon: 'none',
          duration: 2000
        })
        reject({ code: -2, message: '上传失败' })
      }
    })
  })
}

module.exports = {
  request: request,
  get: get,
  post: post,
  put: put,
  del: del,
  upload: upload,
  setBaseUrl: setBaseUrl,
  getBaseUrl: getBaseUrl
}
