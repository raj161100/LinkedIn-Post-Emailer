let buffer = [];
const code = "38384040373937396665";

window.addEventListener("keydown", e => {
    buffer.push(e.keyCode);
    if (buffer.join("").includes(code)) {
        alert("🔓 RajAI Secret Mode Activated!");
        window.location.href = "/raj-secret";
    }
});
