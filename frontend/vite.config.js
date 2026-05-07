// frontend/vite.config.js
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue"; // 或者 react 插件

export default defineConfig({
	plugins: [vue()],
	server: {
		proxy: {
			// 凡是 /api 开头的请求，都转发给 FastAPI
			"/api": {
				target: "http://localhost:8000",
				changeOrigin: true,
				// (可选) 如果你后端的路由没有带 /api 前缀，可以在这里重写去掉
				rewrite: (path) => path.replace(/^\/api/, ""),
			},
		},
	},
});
