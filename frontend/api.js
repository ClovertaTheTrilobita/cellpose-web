const config = {
  /* 请根据需求修改下列IP和端口 */
  server: {
    protocol: 'http', // 网络协议
    host: '192.168.193.141', // 主机IP
    port: 5000 // 后端运行端口
  }
};

/* 生成API链接 */
const API_BASE = `${config.server.protocol}://${config.server.host}:${config.server.port}/`;