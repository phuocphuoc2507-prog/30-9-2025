// static/script.js
document.addEventListener('DOMContentLoaded', () => {
    const socket = io(); // Kết nối đến Backend Python

    // Lấy các phần tử trên trang web
    const videoFeed = document.getElementById('video-feed');
    const messageArea = document.getElementById('message-area');
    const confirmationQuestion = document.getElementById('confirmation-question');
    const addedWeightSpan = document.getElementById('added-weight');
    const timeLeftSpan = document.getElementById('time-left');
    const thankyouMessage = document.getElementById('thankyou-message');
    // Lấy các phần tử hiển thị điểm (MỚI)
    const pointsDisplay = document.getElementById('points-display');
    const pointsEarnedSpan = document.getElementById('points-earned');
    const totalPointsSpan = document.getElementById('total-points');
    const learningTimeLeftSpan = document.getElementById('learning-time-left'); // THÊM MỚI


    // --- THAY ĐỔI: Lấy các phần tử cho cả 2 cân ---
    const binElements = {
        1: {
            progressBar: document.getElementById('progress-bar-1'),
            percentage: document.getElementById('percentage-1'),
            weightKg: document.getElementById('weight-kg-1')
        },
        2: {
            progressBar: document.getElementById('progress-bar-2'),
            percentage: document.getElementById('percentage-2'),
            weightKg: document.getElementById('weight-kg-2')
        }
    };
    const BIN_CAPACITY_KG = 10.0; // Đồng bộ với config.py

    const statusCards = {
        idle: document.getElementById('status-idle'),
        recognizing: document.getElementById('status-recognizing'),
        confirmation: document.getElementById('status-confirmation'),
        failure_learning: document.getElementById('status-failure-learning'),
        weighing: document.getElementById('status-weighing'),
        thankyou: document.getElementById('status-thankyou')
    };

    // Lấy các phần tử form nhập thông tin người lạ
    const unknownInfoForm = document.getElementById('unknown-info-form');
    const inputName = document.getElementById('input-name');
    const inputClass = document.getElementById('input-class');
    const unknownInfoMessage = document.getElementById('unknown-info-message');
    // Xử lý gửi thông tin người lạ lên server
    if (unknownInfoForm) {
        unknownInfoForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const name = inputName.value.trim();
            const className = inputClass.value.trim();
            if (name && className) {
                socket.emit('unknown_info_submit', { name: name, class_name: className });
                unknownInfoMessage.textContent = 'Đã gửi thông tin! Vui lòng chờ...';
                inputName.value = '';
                inputClass.value = '';
            }
        });
    }

    function showStatus(state) {
        Object.values(statusCards).forEach(card => card.style.display = 'none');
        if (statusCards[state]) {
            statusCards[state].style.display = 'block';
        }
    }

    socket.on('connect', () => {
        console.log('Đã kết nối tới máy chủ Python!');
        showStatus('idle');
    });

    socket.on('update_state', (data) => {
        console.log('Trạng thái mới:', data.state);
        showStatus(data.state);
        if (data.message) {
            messageArea.textContent = data.message;
        }
    });

    socket.on('update_frame', (data) => {
        videoFeed.src = `data:image/jpeg;base64,${data.frame}`;
    });

    socket.on('show_confirmation', (data) => {
        showStatus('confirmation');
        confirmationQuestion.textContent = `Bạn có phải là ${data.name}?`;
    });

    // --- THAY ĐỔI: Cập nhật thông tin cho cả 2 cân ---
    socket.on('update_weight', (data) => {
        // Cập nhật Cân 1
        let weight1 = data.weights.bin_1;
        let percentage1 = Math.min(100, (weight1 / BIN_CAPACITY_KG) * 100);
        binElements[1].progressBar.style.width = `${percentage1}%`;
        binElements[1].percentage.textContent = `${percentage1.toFixed(1)}%`;
        binElements[1].weightKg.textContent = `${weight1.toFixed(3)} kg`;

        // Cập nhật Cân 2
        let weight2 = data.weights.bin_2;
        let percentage2 = Math.min(100, (weight2 / BIN_CAPACITY_KG) * 100);
        binElements[2].progressBar.style.width = `${percentage2}%`;
        binElements[2].percentage.textContent = `${percentage2.toFixed(1)}%`;
        binElements[2].weightKg.textContent = `${weight2.toFixed(3)} kg`;

        // Cập nhật thông tin chung
        addedWeightSpan.textContent = Math.round(data.added_weight * 1000); // g
        timeLeftSpan.textContent = data.time_left;
    });

    socket.on('show_thankyou', (data) => {
        showStatus('thankyou');
        thankyouMessage.textContent = data.message;

        // Hiển thị điểm nếu có (MỚI)
        if (data.points_earned > 0) {
            pointsEarnedSpan.textContent = data.points_earned;
            totalPointsSpan.textContent = data.total_points;
            pointsDisplay.style.display = 'block'; // Hiện vùng hiển thị điểm
        } else {
            pointsDisplay.style.display = 'none'; // Ẩn đi nếu không nhận được điểm
        }
    });

    // THÊM MỚI: Lắng nghe sự kiện cập nhật đồng hồ đếm ngược khi học người mới
    socket.on('update_learning_timer', function(data) {
        if (learningTimeLeftSpan) {
            learningTimeLeftSpan.textContent = data.time_left;
        }
    });

    document.getElementById('yes-button').addEventListener('click', () => {
        socket.emit('confirmation_response', { 'response': 'yes' });
    });

    document.getElementById('no-button').addEventListener('click', () => {
        socket.emit('confirmation_response', { 'response': 'no' });
    });

    document.addEventListener('keydown', (event) => {
        if (event.code === 'Space') {
            socket.emit('weighing_mock_add');
        }
    });
});