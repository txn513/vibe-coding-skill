# API 设计规范

## 命名
- RESTful 资源用复数名词: `/users`, `/orders`
- 动作用动词: `POST /orders/{id}/cancel`
- 版本前缀: `/v1/`, `/v2/`

## 请求/响应
- 统一响应格式: `{ code, data, message }`
- 分页参数: `page`, `page_size`，响应含 `total`, `has_more`
- 时间格式: ISO 8601

## 错误码
- 4xx: 客户端错误
- 5xx: 服务端错误
- 业务错误码统一在 `data.code` 中
