"""
recommendation.py - Hybrid Recommendation System
==================================================
Module này triển khai hệ thống gợi ý sản phẩm lai (Hybrid) gồm:

1. Content-based Filtering:
   - Sử dụng TF-IDF Vectorizer trên (Tên + Mô tả + Danh mục) của sản phẩm.
   - Tính Cosine Similarity giữa các sản phẩm.
   - Gợi ý sản phẩm tương tự dựa trên nội dung.

2. Collaborative Filtering:
   - Xây dựng ma trận User-Item từ lịch sử mua hàng (OrderItem).
   - Tính Cosine Similarity giữa các user.
   - Gợi ý sản phẩm mà user tương tự đã mua nhưng user hiện tại chưa mua.

3. Hybrid Score:
   - Score = α * CF_Score + (1 - α) * Content_Score
   - α = 0.5 (mặc định), tự động điều chỉnh khi Cold Start.

Cold Start Handling:
   - User mới (chưa có đơn hàng): α = 0 → gợi ý Content-based / Top Trending.
   - Sản phẩm mới (chưa ai mua): gợi ý cho user thích sản phẩm cùng danh mục.
"""
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class HybridRecommender:
    """
    Hybrid Recommendation System kết hợp Content-based và Collaborative Filtering.
    """

    def __init__(self, alpha=0.5):
        """
        Khởi tạo recommender.
        Args:
            alpha (float): Trọng số cho Collaborative Filtering (0 đến 1).
                           Score = α * CF + (1-α) * Content
        """
        self.alpha = alpha

        # Ma trận TF-IDF và Cosine Similarity cho Content-based
        self.tfidf_matrix = None
        self.content_similarity = None
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words=None  # Tiếng Việt không dùng stop_words mặc định
        )

        # Ma trận User-Item cho Collaborative Filtering
        self.user_item_matrix = None
        self.user_similarity = None

        # Mapping ID ↔ Index
        self.product_ids = []
        self.user_ids = []
        self.product_id_to_idx = {}
        self.user_id_to_idx = {}

    # ==========================================================
    # PHẦN 1: CONTENT-BASED FILTERING
    # ==========================================================

    def fit_content(self, products_df):
        """
        Huấn luyện Content-based model từ DataFrame sản phẩm.

        Args:
            products_df (pd.DataFrame): Cần có cột:
                - id, name, description, category_name
        """
        # Tạo "content string" = tên + mô tả + danh mục (lặp 2 lần để tăng trọng số)
        products_df = products_df.copy()
        products_df['description'] = products_df['description'].fillna('')
        products_df['category_name'] = products_df['category_name'].fillna('')

        products_df['content'] = (
            products_df['name'] + ' ' +
            products_df['description'] + ' ' +
            products_df['category_name'] + ' ' +
            products_df['category_name']  # Lặp category để tăng trọng số danh mục
        )

        # Lưu mapping product_id ↔ index
        self.product_ids = products_df['id'].tolist()
        self.product_id_to_idx = {pid: idx for idx, pid in enumerate(self.product_ids)}

        # Tính TF-IDF matrix
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(products_df['content'])

        # Tính Cosine Similarity giữa tất cả cặp sản phẩm
        # content_similarity[i][j] = độ tương tự giữa SP i và SP j
        self.content_similarity = cosine_similarity(self.tfidf_matrix)

    def get_similar_products(self, product_id, top_n=8):
        """
        Content-based: Tìm top_n sản phẩm tương tự với product_id.

        Args:
            product_id (int): ID sản phẩm gốc.
            top_n (int): Số sản phẩm trả về.

        Returns:
            list[tuple]: [(product_id, similarity_score), ...] sắp xếp giảm dần.
        """
        if product_id not in self.product_id_to_idx:
            return []

        idx = self.product_id_to_idx[product_id]
        # Lấy hàng tương ứng trong ma trận similarity
        sim_scores = list(enumerate(self.content_similarity[idx]))

        # Sắp xếp giảm dần theo điểm, bỏ qua chính nó (index = idx)
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
        sim_scores = [(self.product_ids[i], score) for i, score in sim_scores
                      if i != idx]

        return sim_scores[:top_n]

    # ==========================================================
    # PHẦN 2: COLLABORATIVE FILTERING
    # ==========================================================

    def fit_collaborative(self, orders_df):
        """
        Huấn luyện Collaborative Filtering từ lịch sử đơn hàng.

        Args:
            orders_df (pd.DataFrame): Cần có cột:
                - user_id, product_id, quantity
        """
        if orders_df.empty:
            self.user_item_matrix = None
            self.user_similarity = None
            return

        # Tạo ma trận User-Item: hàng = user, cột = product, giá trị = tổng quantity
        # Nếu user A mua SP X 3 lần → user_item_matrix[A][X] = 3
        self.user_item_matrix = orders_df.pivot_table(
            index='user_id',
            columns='product_id',
            values='quantity',
            aggfunc='sum',
            fill_value=0
        )

        self.user_ids = self.user_item_matrix.index.tolist()
        self.user_id_to_idx = {uid: idx for idx, uid in enumerate(self.user_ids)}

        # Tính Cosine Similarity giữa các user
        # user_similarity[i][j] = mức tương tự hành vi mua sắm giữa user i và j
        if len(self.user_ids) > 1:
            self.user_similarity = cosine_similarity(self.user_item_matrix.values)
        else:
            self.user_similarity = np.array([[1.0]])

    def get_cf_recommendations(self, user_id, top_n=8):
        """
        Collaborative Filtering: Gợi ý sản phẩm dựa trên hành vi user tương tự.

        Thuật toán:
        1. Tìm K user tương tự nhất (K=10).
        2. Với mỗi sản phẩm chưa mua, tính điểm = trung bình có trọng số
           (weighted average) dựa trên similarity × purchase quantity.
        3. Trả về top_n sản phẩm điểm cao nhất.

        Args:
            user_id (int): ID user cần gợi ý.
            top_n (int): Số sản phẩm trả về.

        Returns:
            dict: {product_id: cf_score} hoặc {} nếu user mới.
        """
        if (self.user_item_matrix is None or
                user_id not in self.user_id_to_idx):
            return {}

        user_idx = self.user_id_to_idx[user_id]

        # Lấy similarity scores với tất cả user khác
        sim_scores = self.user_similarity[user_idx]

        # Tìm K=10 user tương tự nhất (bỏ qua chính mình)
        k = min(10, len(self.user_ids) - 1)
        if k <= 0:
            return {}

        similar_user_indices = np.argsort(sim_scores)[::-1][1:k + 1]

        # Lấy danh sách sản phẩm user hiện tại ĐÃ mua
        user_purchases = set(
            self.user_item_matrix.columns[
                self.user_item_matrix.iloc[user_idx] > 0
            ].tolist()
        )

        # Tính điểm CF cho từng sản phẩm CHƯA mua
        cf_scores = {}
        for prod_col in self.user_item_matrix.columns:
            if prod_col in user_purchases:
                continue  # Bỏ qua sản phẩm đã mua

            # Weighted sum: Σ(similarity[i] × purchase_quantity[i]) / Σ|similarity[i]|
            numerator = 0
            denominator = 0
            for sim_idx in similar_user_indices:
                sim_weight = sim_scores[sim_idx]
                purchase_val = self.user_item_matrix.iloc[sim_idx][prod_col]
                numerator += sim_weight * purchase_val
                denominator += abs(sim_weight)

            if denominator > 0:
                cf_scores[prod_col] = numerator / denominator

        return cf_scores

    # ==========================================================
    # PHẦN 3: HYBRID (KẾT HỢP)
    # ==========================================================

    def get_hybrid_recommendations(self, user_id, purchased_product_ids=None, top_n=8):
        """
        Gợi ý Hybrid: Kết hợp CF + Content-based.

        Công thức: Score = α * CF_Score + (1-α) * Content_Score

        Cold Start:
        - User mới (chưa mua gì): α = 0 → 100% Content-based / Top Trending.
        - User cũ: α = self.alpha (mặc định 0.5).

        Args:
            user_id (int): ID user.
            purchased_product_ids (list): Danh sách product_id user đã mua.
            top_n (int): Số sản phẩm gợi ý.

        Returns:
            list[tuple]: [(product_id, hybrid_score), ...] sắp xếp giảm dần.
        """
        if purchased_product_ids is None:
            purchased_product_ids = []

        purchased_set = set(purchased_product_ids)

        # ---- Xử lý Cold Start: User mới ----
        is_new_user = (user_id not in self.user_id_to_idx) or len(purchased_product_ids) == 0

        if is_new_user:
            alpha = 0  # 100% Content-based
        else:
            alpha = self.alpha

        # ---- Bước 1: Lấy CF Scores ----
        cf_scores = {}
        if alpha > 0:
            cf_scores = self.get_cf_recommendations(user_id, top_n=top_n * 3)

        # ---- Bước 2: Lấy Content Scores ----
        # Dựa trên sản phẩm đã mua, tính trung bình content similarity
        content_scores = {}
        if self.content_similarity is not None:
            if len(purchased_product_ids) > 0:
                for pid in self.product_ids:
                    if pid in purchased_set:
                        continue  # Bỏ qua SP đã mua

                    if pid not in self.product_id_to_idx:
                        continue

                    # Trung bình similarity với tất cả SP đã mua
                    pid_idx = self.product_id_to_idx[pid]
                    sim_sum = 0
                    count = 0
                    for bought_pid in purchased_product_ids:
                        if bought_pid in self.product_id_to_idx:
                            bought_idx = self.product_id_to_idx[bought_pid]
                            sim_sum += self.content_similarity[pid_idx][bought_idx]
                            count += 1

                    if count > 0:
                        content_scores[pid] = sim_sum / count
            else:
                # User mới chưa mua gì → Content score = 0 (sẽ fallback Top Trending)
                pass

        # ---- Bước 3: Kết hợp Hybrid Score ----
        all_product_ids = set(cf_scores.keys()) | set(content_scores.keys())
        hybrid_scores = []

        for pid in all_product_ids:
            if pid in purchased_set:
                continue

            cf_val = cf_scores.get(pid, 0)
            content_val = content_scores.get(pid, 0)

            # Normalize CF scores về [0, 1] nếu có
            # (Content similarity đã nằm trong [0, 1] sẵn)
            hybrid_score = alpha * cf_val + (1 - alpha) * content_val
            hybrid_scores.append((pid, hybrid_score))

        # Sắp xếp giảm dần theo điểm
        hybrid_scores.sort(key=lambda x: x[1], reverse=True)

        return hybrid_scores[:top_n]

    def get_top_trending(self, products_df, top_n=8, exclude_ids=None):
        """
        Fallback: Trả về sản phẩm bán chạy nhất (Top Trending).
        Dùng khi user mới hoàn toàn chưa có dữ liệu.

        Args:
            products_df (pd.DataFrame): Cần cột: id, total_sold
            top_n (int): Số sản phẩm trả về.
            exclude_ids (set): Các product_id cần loại trừ.

        Returns:
            list[int]: Danh sách product_id bán chạy nhất.
        """
        if exclude_ids is None:
            exclude_ids = set()

        trending = (
            products_df[~products_df['id'].isin(exclude_ids)]
            .sort_values('total_sold', ascending=False)
            .head(top_n)
        )
        return trending['id'].tolist()


# ==========================================================
# HÀM TIỆN ÍCH: Được gọi từ app.py
# ==========================================================

def build_recommender(db_session, alpha=0.5):
    """
    Xây dựng recommender từ dữ liệu trong database.
    Gọi hàm này mỗi khi cần cập nhật model (hoặc cache theo thời gian).

    Args:
        db_session: SQLAlchemy session.
        alpha (float): Tham số hybrid.

    Returns:
        HybridRecommender: Instance đã được huấn luyện.
    """
    from models import Product, Category, Order, OrderItem

    recommender = HybridRecommender(alpha=alpha)

    # ---- 1. Chuẩn bị dữ liệu sản phẩm cho Content-based ----
    products = db_session.query(
        Product.id,
        Product.name,
        Product.description,
        Product.total_sold,
        Category.name.label('category_name')
    ).join(Category, Product.category_id == Category.id).filter(
        Product.is_active == True
    ).all()

    if not products:
        return recommender

    products_df = pd.DataFrame(products, columns=[
        'id', 'name', 'description', 'total_sold', 'category_name'
    ])

    recommender.fit_content(products_df)

    # ---- 2. Chuẩn bị dữ liệu đơn hàng cho Collaborative Filtering ----
    # Lấy tất cả order_items từ đơn hàng đã hoàn thành (completed)
    order_items = db_session.query(
        Order.user_id,
        OrderItem.product_id,
        OrderItem.quantity
    ).join(OrderItem, Order.id == OrderItem.order_id).filter(
        Order.status.in_(['completed', 'pending', 'confirmed', 'shipping'])
    ).all()

    if order_items:
        orders_df = pd.DataFrame(order_items, columns=[
            'user_id', 'product_id', 'quantity'
        ])
        recommender.fit_collaborative(orders_df)

    return recommender


def get_recommendations_for_user(recommender, user_id, db_session, top_n=8):
    """
    Lấy danh sách sản phẩm gợi ý cho 1 user cụ thể.

    Args:
        recommender (HybridRecommender): Model đã huấn luyện.
        user_id (int): ID user (có thể None nếu chưa đăng nhập).
        db_session: SQLAlchemy session.
        top_n (int): Số sản phẩm gợi ý.

    Returns:
        list[int]: Danh sách product_id được gợi ý.
    """
    from models import Product, Category, Order, OrderItem

    # Nếu chưa đăng nhập hoặc user_id = None → Top Trending
    if user_id is None:
        products = db_session.query(
            Product.id, Product.total_sold
        ).filter(Product.is_active == True).all()

        products_df = pd.DataFrame(products, columns=['id', 'total_sold'])
        return recommender.get_top_trending(products_df, top_n=top_n)

    # Lấy danh sách sản phẩm user đã mua
    purchased = db_session.query(OrderItem.product_id).join(
        Order, OrderItem.order_id == Order.id
    ).filter(Order.user_id == user_id).distinct().all()

    purchased_ids = [p[0] for p in purchased]

    # Gọi Hybrid Recommendation
    recommendations = recommender.get_hybrid_recommendations(
        user_id=user_id,
        purchased_product_ids=purchased_ids,
        top_n=top_n
    )

    # Nếu Hybrid không đủ kết quả → bổ sung bằng Top Trending
    recommended_ids = [pid for pid, score in recommendations]

    if len(recommended_ids) < top_n:
        products = db_session.query(
            Product.id, Product.total_sold
        ).filter(Product.is_active == True).all()

        products_df = pd.DataFrame(products, columns=['id', 'total_sold'])
        exclude = set(recommended_ids) | set(purchased_ids)
        trending = recommender.get_top_trending(
            products_df,
            top_n=top_n - len(recommended_ids),
            exclude_ids=exclude
        )
        recommended_ids.extend(trending)

    return recommended_ids[:top_n]
