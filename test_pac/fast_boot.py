import os
from flask import Flask, render_template
# 注意这里：如果是安装的 bootstrap-flask，通常这样导入
from flask_bootstrap import Bootstrap5 

app = Flask(__name__)
bootstrap = Bootstrap5(app)

# ... 后面代码不变
# 路由定义
@app.route('/')
def index():
    # 模拟从数据库获取的数据
    user_info = {"name": "Master", "status": "Active"}
    return render_template('index.html', user=user_info)

@app.route('/logs')
def logs():
    # 模拟路由跳转到日志页
    return "这是识别日志页面"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)