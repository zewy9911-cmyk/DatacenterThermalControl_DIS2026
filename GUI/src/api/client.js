import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 5000 })

export const getStatus       = ()                    => http.get('/status')
export const setFanSpeed     = (speed)               => http.post('/fan',        { speed })
export const setValve        = (id, open)            => http.post('/valve',      { valve_id: id, open })
export const setMode         = (mode)                => http.post('/mode',       { mode })
export const getHistory      = (hours = 24)          => http.get('/history',     { params: { hours } })
export const getStatistics   = ()                    => http.get('/statistics')
export const getEvents       = (limit = 50)          => http.get('/events',      { params: { limit } })
export const getSnmpInfo     = ()                    => http.get('/snmp')
export const getThresholds   = ()                    => http.get('/thresholds')
export const setThresholds   = (data)                => http.post('/thresholds', data)
export const getSimulation   = ()                    => http.get('/simulation')
export const setSimulation   = (enabled, temperature, humidity) =>
  http.post('/simulation', { enabled, temperature, humidity })

