<template>
	<div class="min-h-screen bg-gray-50 flex flex-col md:flex-row font-sans">
		<aside
			class="w-full md:w-80 bg-white border-r border-gray-200 p-6 flex flex-col"
		>
			<div class="flex items-center gap-2 mb-8">
				<BookOpen class="w-6 h-6 text-blue-600" />
				<h1 class="text-xl font-bold text-gray-800">教研知识引擎</h1>
			</div>

			<div
				class="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center hover:border-blue-400 hover:bg-blue-50 transition cursor-pointer relative"
			>
				<input
					type="file"
					@change="uploadPDF"
					accept=".pdf"
					class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
				/>
				<UploadCloud class="w-8 h-8 text-gray-400 mx-auto mb-2" />
				<span class="text-sm font-medium text-gray-700"
					>点击上传教辅 PDF</span
				>
				<span class="block text-xs text-gray-400 mt-1"
					>调用 MinerU VLM 提取入库</span
				>

				<div
					v-if="uploadStatus"
					class="mt-4 text-xs font-semibold text-blue-600 animate-pulse"
				>
					{{ uploadStatus }}
				</div>
			</div>
		</aside>

		<main class="flex-1 flex flex-col h-screen relative">
			<div
				class="flex-1 overflow-y-auto p-6 md:p-10 pb-48"
				ref="chatContainer"
			>
				<div class="max-w-3xl mx-auto space-y-6">
					<div
						v-for="(msg, index) in chatHistory"
						:key="index"
						class="animate-fade-in"
					>
						<div
							v-if="msg.role === 'user'"
							class="flex justify-end mb-4"
						>
							<div
								class="bg-blue-50 border border-blue-100 rounded-2xl rounded-tr-sm p-4 max-w-[85%]"
							>
								<img
									v-if="msg.image"
									:src="msg.image"
									class="rounded border border-gray-200 max-h-40 mb-2 object-contain"
								/>
								<p class="text-gray-800 whitespace-pre-wrap">
									{{ msg.content }}
								</p>
							</div>
						</div>

						<div
							v-if="msg.role === 'agent'"
							class="flex justify-start"
						>
							<div
								class="w-8 h-8 bg-black rounded-lg flex items-center justify-center text-white mr-3 shrink-0 mt-1"
							>
								<Bot class="w-5 h-5" />
							</div>
							<div class="flex-1 max-w-[85%]">
								<details
									class="mb-3 bg-indigo-50/50 border border-indigo-100 rounded-xl overflow-hidden group shadow-sm"
									:open="
										msg.status === 'thinking' ||
										msg.steps.length > 0
									"
								>
									<summary
										class="flex items-center gap-2 px-4 py-3 cursor-pointer text-sm font-medium text-indigo-800 list-none"
									>
										<Loader2
											v-if="msg.status === 'thinking'"
											class="w-4 h-4 animate-spin"
										/>
										<Sparkles
											v-else
											class="w-4 h-4 text-indigo-500"
										/>
										{{
											msg.status === "thinking"
												? "教研大脑深度思考中..."
												: "教研推理完成"
										}}
										<ChevronDown
											class="w-4 h-4 ml-auto transition-transform group-open:rotate-180"
										/>
									</summary>

									<div
										class="px-4 pb-3 pt-1 border-t border-indigo-100/50"
										v-if="msg.steps.length > 0"
									>
										<div
											class="border-l-2 border-indigo-200 pl-4 space-y-4 mt-2"
										>
											<div
												v-for="(
													step, sIdx
												) in msg.steps"
												:key="sIdx"
												class="relative"
											>
												<div
													class="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-indigo-400 ring-4 ring-indigo-50"
												></div>
												<p
													class="text-sm font-semibold text-gray-700"
												>
													{{ getNodeName(step.node) }}
												</p>
												<Markdown
													class="text-xs text-gray-500 mt-1"
													:content="step.details"
												/>
											</div>
										</div>
									</div>
									<div
										v-else
										class="px-4 py-3 text-xs text-gray-400 border-t border-indigo-100/50"
									>
										暂无详细推理日志
									</div>
								</details>

								<div
									v-if="msg.pdf_student || msg.pdf_teacher"
									class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm mt-4 mb-2"
								>
									<h4
										class="font-bold text-gray-800 mb-3 flex items-center gap-2"
									>
										<CheckCircle2
											class="w-5 h-5 text-green-500"
										/>
										试卷编译成功
									</h4>
									<div class="flex flex-wrap gap-3">
										<button
											v-if="msg.pdf_teacher"
											@click="
												downloadPDF(
													`http://localhost:8000${msg.pdf_teacher}`,
													msg.download_name_teacher,
												)
											"
											class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition cursor-pointer"
										>
											<Download class="w-4 h-4" />
											教师解析版
										</button>
										<button
											v-if="msg.pdf_student"
											@click="
												downloadPDF(
													`http://localhost:8000${msg.pdf_student}`,
													msg.download_name_student,
												)
											"
											class="flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition cursor-pointer"
										>
											<Download class="w-4 h-4" />
											学生空白版
										</button>
									</div>
								</div>

								<div
									v-if="msg.error"
									class="bg-red-50 text-red-600 p-4 rounded-xl text-sm border border-red-100 mt-2"
								>
									出错了: {{ msg.error }}
								</div>
							</div>
						</div>
					</div>
					<div ref="scrollAnchor" class="h-4"></div>
				</div>
			</div>

			<div
				class="absolute bottom-0 w-full bg-white border-t p-4 px-6 md:px-10 z-10 shadow-[0_-10px_30px_rgba(0,0,0,0.05)]"
			>
				<div class="max-w-3xl mx-auto">
					<div v-if="imgPreview" class="relative inline-block mb-3">
						<img
							:src="imgPreview"
							class="h-16 rounded border shadow-sm"
						/>
						<button
							@click="
								imgPreview = null;
								imgFile = null;
							"
							class="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-0.5 shadow"
						>
							<X class="w-3 h-3" />
						</button>
					</div>

					<div class="flex items-end gap-3">
						<label
							class="p-3 text-gray-500 hover:text-blue-600 cursor-pointer bg-gray-100 rounded-xl transition shrink-0"
						>
							<input
								type="file"
								class="hidden"
								@change="handleImage"
								accept="image/*,.pdf"
							/>
							<ImagePlus class="w-5 h-5" />
						</label>

						<textarea
							v-model="prompt"
							@keydown.enter.prevent="sendTask"
							:disabled="isProcessing"
							placeholder="描述出题需求，或上传题目图片寻找相似题..."
							class="flex-1 bg-gray-100 text-sm p-4 rounded-xl outline-none resize-none disabled:opacity-50"
							rows="1"
						></textarea>

						<button
							@click="sendTask"
							:disabled="isProcessing || (!prompt && !imgFile)"
							class="bg-black text-white p-3.5 rounded-xl hover:bg-gray-800 disabled:opacity-30 transition shrink-0"
						>
							<Send class="w-5 h-5" />
						</button>
					</div>
				</div>
			</div>
		</main>
	</div>
</template>

<script setup>
import { ref, nextTick } from "vue";
import {
	BookOpen,
	UploadCloud,
	Loader2,
	Sparkles,
	ChevronDown,
	CheckCircle2,
	Download,
	ImagePlus,
	Send,
	X,
	Bot,
} from "lucide-vue-next";
import Markdown from "./components/Markdown.vue"; // 确保路径正确

const chatContainer = ref(null);
const scrollAnchor = ref(null); // 新增滚动锚点
const chatHistory = ref([]);
const prompt = ref("");
const imgFile = ref(null);
const imgPreview = ref(null);
const isProcessing = ref(false);

const uploadStatus = ref("");

// 节点名称中文映射
const getNodeName = (node) => {
	const map = {
		parse: "多模态意图与考点分析",
		retrieve: "内网私有库与互联网并发检索",
		review: "LLM 深度逻辑推理与淘汰去噪",
		compile: "自动化 LaTeX 排版与 PDF 渲染",
	};
	return map[node] || node;
};

const scrollToBottom = async () => {
	await nextTick();
	if (scrollAnchor.value) {
		scrollAnchor.value.scrollIntoView({ behavior: "smooth", block: "end" });
	}
};

// 图片选择与预览
const handleImage = (e) => {
	const file = e.target.files[0];
	if (file) {
		imgFile.value = file;
		const reader = new FileReader();
		reader.onload = (e) => {
			imgPreview.value = e.target.result;
		};
		reader.readAsDataURL(file);
	}
	e.target.value = "";
};

// 知识库上传 (MinerU)
const uploadPDF = async (e) => {
	const file = e.target.files[0];
	if (!file) return;

	const formData = new FormData();
	formData.append("file", file);

	uploadStatus.value = "上传中...";
	try {
		const res = await fetch("http://localhost:8000/upload_knowledge", {
			method: "POST",
			body: formData,
		});
		uploadStatus.value = res.ok ? "提交成功，云端解析中" : "服务异常";
	} catch (err) {
		uploadStatus.value = "网络错误";
	}
	setTimeout(() => {
		uploadStatus.value = "";
	}, 3000);
};

// 使用 blob 方式下载 PDF，确保文件名正确
const downloadPDF = async (url, filename) => {
	try {
		const response = await fetch(url);
		const blob = await response.blob();
		const blobUrl = window.URL.createObjectURL(blob);

		const link = document.createElement("a");
		link.href = blobUrl;
		link.download = filename;
		document.body.appendChild(link);
		link.click();

		// 清理
		document.body.removeChild(link);
		window.URL.revokeObjectURL(blobUrl);
	} catch (error) {
		console.error("下载文件失败:", error);
	}
};

// 核心流式对话发送
const sendTask = async () => {
	if (isProcessing.value || (!prompt.value && !imgFile.value)) return;

	chatHistory.value.push({
		role: "user",
		content: prompt.value,
		image: imgPreview.value,
	});

	const agentIdx =
		chatHistory.value.push({
			role: "agent",
			status: "thinking",
			steps: [],
			pdf_student: "",
			pdf_teacher: "",
			download_name_student: "",
			download_name_teacher: "",
			error: null,
		}) - 1;

	const currentMsg = chatHistory.value[agentIdx];

	const formData = new FormData();
	formData.append("prompt", prompt.value);
	if (imgFile.value) formData.append("reference_file", imgFile.value);

	isProcessing.value = true;
	prompt.value = "";
	imgFile.value = null;
	imgPreview.value = null;
	scrollToBottom();

	try {
		const res = await fetch("http://localhost:8000/chat", {
			method: "POST",
			body: formData,
		});

		if (!res.ok) {
			throw new Error(`HTTP error! status: ${res.status}`);
		}

		const reader = res.body.getReader();
		const decoder = new TextDecoder();

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			const lines = decoder.decode(value, { stream: true }).split("\n\n");
			for (const line of lines) {
				if (line.startsWith("data: ")) {
					try {
						const data = JSON.parse(line.substring(6));
						if (data.node !== "finish") {
							currentMsg.steps.push(data);
						}

						if (data.status === "done" && data.node === "finish") {
							currentMsg.status = "done";
							currentMsg.pdf_student = data.pdf_student || "";
							currentMsg.pdf_teacher = data.pdf_teacher || "";
							currentMsg.download_name_student =
								data.download_name_student || "学生卷.pdf";
							currentMsg.download_name_teacher =
								data.download_name_teacher || "解析卷.pdf";
						}
						scrollToBottom();
					} catch (e) {
						console.warn("解析单条 JSON 流数据失败:", e, line);
					}
				}
			}
		}
	} catch (error) {
		console.error("请求发生错误:", error);
		currentMsg.status = "error";
		currentMsg.error = "请求中断或后端无响应，请检查终端日志。";
	} finally {
		if (currentMsg.status === "thinking") currentMsg.status = "error";
		isProcessing.value = false;
		scrollToBottom();
	}
};
</script>

<style>
@tailwind base;
@tailwind components;
@tailwind utilities;

.animate-fade-in {
	animation: fadeIn 0.4s ease-out forwards;
}
@keyframes fadeIn {
	from {
		opacity: 0;
		transform: translateY(10px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}
</style>
